# Using it from a phone

From a phone's browser you can use the chat page of the Sync-Strata running on your PC. Nothing needs to be installed on the phone.

## On the same Wi-Fi (QR code)

1. In the settings **on the PC's screen**, set "Phone connection" to "Same Wi-Fi" (this setting can be changed only on the PC's screen and from the CLI).
2. Press "Apply now (restart dsh)". The setting takes effect when dsh restarts (a reply in progress stops; the engine keeps running).
3. Scan the QR code that appears with the camera of a phone on the same Wi-Fi, and the chat page opens.

The QR code is a one-time pass that works once, for 3 minutes. The long-lived key never leaves the PC. If it expires, press "New QR code".

**On the same Wi-Fi the connection is not encrypted (http).** Use it on a Wi-Fi you trust, such as at home.

## From outside (Tailscale)

1. Install [Tailscale](https://tailscale.com/) on both the PC and the phone, and log in to the same account.
2. In the settings on the PC's screen, set "Phone connection" to "Tailscale" and press "Apply now".
3. Scan the QR code that appears with the phone (keep Tailscale on on the phone).

Tailscale encrypts the connection. Opening a port directly to the internet is not recommended.

## From the CLI

```
sync settings set lan_remote lan       # off, lan or tailscale
sync remote-apply                      # restart only dsh and the relay to apply it
sync remote-url                        # the URL to connect to now
sync remote-url --pair                 # connect a phone without the GUI (a one-time URL and QR code for 3 minutes)
```

## If it cannot connect

- Is the phone on the same Wi-Fi (not on mobile data)?
- Does Windows Firewall allow `dsh-node.exe` (Node.js) on private networks? (On Linux: does the firewall, such as ufw, allow the relay's port from the LAN?)
- Is the PC's Wi-Fi network set to "Private"? (It cannot connect on "Public".)
- With Tailscale: is Tailscale on and logged in on both the PC and the phone?
- **When the PC's address changes** (a router restart, another Wi-Fi, etc.), restart with "Apply now" or `sync remote-apply`, then scan a new QR code.

## Notes

- A phone's login ends 30 days after the day it scanned the QR code. When 7 days or fewer are left, a warning appears on the phone's screen and in "Connected devices" on the PC. To extend it, scan the QR code on the PC again. If you lose your phone, take its login back in "Connected devices" on the PC. A device whose login is taken back stops working right away.
- Even when set to "Off", it stays connected until dsh restarts.
- When the PC sleeps, it cannot be used from the phone either.
