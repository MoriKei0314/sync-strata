// 会話の画面（WebView2 / WebKitGTK）の子プロセスの優先度を下げ，エンジン（Strata）と CPU・GPU を取り合わないようにする（11/16 係 T2）．
// 下げるだけで，上げることはしない．Strata 側のプロセスには触らない（枠自身の子孫だけを見る）．
//   low    : CPU を BELOW_NORMAL，GPU の優先度を BELOW_NORMAL（既定）
//   idle   : CPU を IDLE＋EcoQoS，GPU の優先度を IDLE（画面のなめらかさは落ちうる）
//   cpu-low: CPU だけ BELOW_NORMAL．GPU の優先度は触らない（Strata が GPU を使い続ける間も画面のコマを遅らせない．11/16 係 T3）
//   normal : 何もしない
// Linux は WebKitGTK の子に nice（low=+5，idle=+15）と ioprio を付ける．GPU の優先度は Linux に共通の手段が無いので触らない．

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Prio {
    Normal,
    Low,
    Idle,
    CpuLow,
}

impl Prio {
    pub fn parse(s: &str) -> Prio {
        match s.trim().to_ascii_lowercase().as_str() {
            "normal" | "off" | "none" => Prio::Normal,
            "idle" | "lowest" => Prio::Idle,
            "cpu-low" | "cpu_low" | "cpulow" | "cpu" => Prio::CpuLow,
            _ => Prio::Low,
        }
    }
    pub fn name(self) -> &'static str {
        match self {
            Prio::Normal => "normal",
            Prio::Low => "low",
            Prio::Idle => "idle",
            Prio::CpuLow => "cpu-low",
        }
    }
}

/// 子プロセスの見張りを始める（窓を作った後に 1 回呼ぶ）．
pub fn start(prio: Prio, log: impl Fn(&str) + Send + 'static) {
    if prio == Prio::Normal {
        log("gui_priority=normal: 画面の子プロセスの優先度は触らない");
        return;
    }
    let _ = std::thread::Builder::new().name("gui-prio".into()).spawn(move || {
        let mut done: std::collections::HashSet<u32> = std::collections::HashSet::new();
        let mut tick = 0u32;
        loop {
            let live = imp::apply_all(prio, &mut done, &log);
            done.retain(|p| live.contains(p));
            tick += 1;
            // 起動の直後は子が次々に増えるので細かく，落ち着いたら間を空ける．
            std::thread::sleep(std::time::Duration::from_millis(if tick < 30 { 500 } else { 2000 }));
        }
    });
}

#[cfg(windows)]
mod imp {
    use super::Prio;
    use std::collections::{HashMap, HashSet};

    type Handle = *mut core::ffi::c_void;

    #[repr(C)]
    struct ProcessEntry32W {
        size: u32,
        usage: u32,
        pid: u32,
        heap: usize,
        module: u32,
        threads: u32,
        ppid: u32,
        pri: i32,
        flags: u32,
        exe: [u16; 260],
    }
    #[repr(C)]
    struct PowerThrottling {
        version: u32,
        control: u32,
        state: u32,
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn CreateToolhelp32Snapshot(flags: u32, pid: u32) -> Handle;
        fn Process32FirstW(h: Handle, e: *mut ProcessEntry32W) -> i32;
        fn Process32NextW(h: Handle, e: *mut ProcessEntry32W) -> i32;
        fn OpenProcess(access: u32, inherit: i32, pid: u32) -> Handle;
        fn CloseHandle(h: Handle) -> i32;
        fn SetPriorityClass(h: Handle, class: u32) -> i32;
        fn GetPriorityClass(h: Handle) -> u32;
        fn SetProcessInformation(h: Handle, class: i32, info: *const core::ffi::c_void, size: u32) -> i32;
        fn GetCurrentProcessId() -> u32;
    }
    #[link(name = "gdi32")]
    extern "system" {
        // D3DKMT_SCHEDULINGPRIORITYCLASS: 0 IDLE, 1 BELOW_NORMAL, 2 NORMAL, ...
        fn D3DKMTSetProcessSchedulingPriorityClass(h: Handle, class: i32) -> i32;
    }

    const PROCESS_SET_INFORMATION: u32 = 0x0200;
    const PROCESS_QUERY_LIMITED_INFORMATION: u32 = 0x1000;
    const BELOW_NORMAL: u32 = 0x4000;
    const IDLE: u32 = 0x0040;
    const TH32CS_SNAPPROCESS: u32 = 2;
    const PROCESS_POWER_THROTTLING: i32 = 4;

    fn snapshot() -> Vec<(u32, u32, String)> {
        let mut v = Vec::new();
        unsafe {
            let s = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
            if s.is_null() || s as isize == -1 {
                return v;
            }
            let mut e: ProcessEntry32W = core::mem::zeroed();
            e.size = core::mem::size_of::<ProcessEntry32W>() as u32;
            let mut ok = Process32FirstW(s, &mut e);
            while ok != 0 {
                let n = e.exe.iter().position(|&c| c == 0).unwrap_or(260);
                v.push((e.pid, e.ppid, String::from_utf16_lossy(&e.exe[..n])));
                ok = Process32NextW(s, &mut e);
            }
            CloseHandle(s);
        }
        v
    }

    /// 枠の子孫の msedgewebview2.exe を全部見つけて優先度を下げる．戻り値は今いる対象の pid．
    pub fn apply_all(prio: Prio, done: &mut HashSet<u32>, log: &dyn Fn(&str)) -> HashSet<u32> {
        let procs = snapshot();
        let me = unsafe { GetCurrentProcessId() };
        let mut kids: HashMap<u32, Vec<u32>> = HashMap::new();
        for (pid, ppid, _) in &procs {
            kids.entry(*ppid).or_default().push(*pid);
        }
        let names: HashMap<u32, &str> = procs.iter().map(|(p, _, n)| (*p, n.as_str())).collect();
        let mut live = HashSet::new();
        let mut stack = vec![me];
        let mut seen = HashSet::new();
        while let Some(p) = stack.pop() {
            for &c in kids.get(&p).map(|v| v.as_slice()).unwrap_or(&[]) {
                if !seen.insert(c) {
                    continue;
                }
                stack.push(c);
                if names.get(&c).map_or(false, |n| n.eq_ignore_ascii_case("msedgewebview2.exe")) {
                    live.insert(c);
                    if !done.contains(&c) {
                        done.insert(c);
                        set_one(c, prio, log);
                    }
                }
            }
        }
        live
    }

    fn set_one(pid: u32, prio: Prio, log: &dyn Fn(&str)) {
        unsafe {
            let h = OpenProcess(PROCESS_SET_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
            if h.is_null() {
                log(&format!("gui_priority: pid {pid} を開けない"));
                return;
            }
            let (cls, gpu) = if prio == Prio::Idle { (IDLE, 0) } else { (BELOW_NORMAL, 1) };
            let cpu_ok = SetPriorityClass(h, cls) != 0;
            let mut eco_ok = true;
            if prio == Prio::Idle {
                let st = PowerThrottling { version: 1, control: 1, state: 1 };
                eco_ok = SetProcessInformation(h, PROCESS_POWER_THROTTLING, &st as *const _ as *const _, 12) != 0;
            }
            let gpu_status = if prio == Prio::CpuLow { 0xffff_ffffu32 as i32 } else { D3DKMTSetProcessSchedulingPriorityClass(h, gpu) };
            let now = GetPriorityClass(h);
            log(&format!(
                "gui_priority={}: WebView2 pid {pid} CPU {} (class 0x{now:x}) EcoQoS {} GPU status 0x{:x}（0xffffffff は GPU を触らない）",
                prio.name(),
                if cpu_ok { "ok" } else { "失敗" },
                if prio == Prio::Idle {
                    if eco_ok {
                        "ok"
                    } else {
                        "失敗"
                    }
                } else {
                    "-"
                },
                gpu_status as u32
            ));
            CloseHandle(h);
        }
    }
}

#[cfg(target_os = "linux")]
mod imp {
    use super::Prio;
    use std::collections::{HashMap, HashSet};

    pub fn apply_all(prio: Prio, done: &mut HashSet<u32>, log: &dyn Fn(&str)) -> HashSet<u32> {
        let mut parent: HashMap<u32, u32> = HashMap::new();
        let mut comm: HashMap<u32, String> = HashMap::new();
        if let Ok(rd) = std::fs::read_dir("/proc") {
            for e in rd.flatten() {
                let Some(pid) = e.file_name().to_str().and_then(|s| s.parse::<u32>().ok()) else { continue };
                let Ok(stat) = std::fs::read_to_string(e.path().join("stat")) else { continue };
                // pid (comm) state ppid ...
                let (Some(l), Some(r)) = (stat.find('('), stat.rfind(')')) else { continue };
                let rest: Vec<&str> = stat[r + 1..].split_whitespace().collect();
                if let Some(pp) = rest.get(1).and_then(|s| s.parse::<u32>().ok()) {
                    parent.insert(pid, pp);
                    comm.insert(pid, stat[l + 1..r].to_string());
                }
            }
        }
        let me = std::process::id();
        let mut live = HashSet::new();
        for (&pid, c) in &comm {
            if !c.starts_with("WebKit") {
                continue;
            }
            // 枠の子孫か（親をたどる）．
            let mut p = pid;
            let mut ok = false;
            for _ in 0..16 {
                match parent.get(&p) {
                    Some(&pp) if pp == me => {
                        ok = true;
                        break;
                    }
                    Some(&pp) if pp > 1 => p = pp,
                    _ => break,
                }
            }
            if !ok {
                continue;
            }
            live.insert(pid);
            if done.insert(pid) {
                let nice = if prio == Prio::Idle { 15 } else { 5 };
                let r = unsafe { libc::setpriority(libc::PRIO_PROCESS, pid as libc::id_t, nice) };
                // ioprio_set(IOPRIO_WHO_PROCESS=1, pid, class<<13|data)．best-effort(2) の最低(7)．
                let io = unsafe { libc::syscall(libc::SYS_ioprio_set, 1i64, pid as i64, (2i64 << 13) | 7) };
                log(&format!(
                    "gui_priority={}: {c} pid {pid} nice {nice} {} ioprio {}",
                    prio.name(),
                    if r == 0 { "ok" } else { "失敗" },
                    if io == 0 { "ok" } else { "失敗" }
                ));
            }
        }
        live
    }
}

#[cfg(not(any(windows, target_os = "linux")))]
mod imp {
    use super::Prio;
    use std::collections::HashSet;
    pub fn apply_all(_: Prio, _: &mut HashSet<u32>, _: &dyn Fn(&str)) -> HashSet<u32> {
        HashSet::new()
    }
}
