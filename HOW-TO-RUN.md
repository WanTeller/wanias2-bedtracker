# Running WaniaS2 BedTracker for testing

A step-by-step guide for someone who has never used Python or a command line.
Everything happens in one window and there is nothing to install.

---

## Part 1 — Open a command window in the project folder

1. Open **File Explorer** (the yellow folder icon on the taskbar).
2. Go to this folder:
   `Desktop` → `WanTeller` → `Projects` → `BedTracker`
3. Click once in the **white address bar** at the top of the File Explorer
   window (where it shows the folder path). The text will turn blue.
4. Type **`powershell`** over it and press **Enter**.
5. A blue or black window opens. The line at the bottom should end with
   `...\Projects\BedTracker>`. Leave this window open — you type commands here.

> Tip: to paste a command into this window, right-click inside it.

---

## Part 2 — Turn ON the simple testing login (one time)

Copy this line, paste it into the window, press **Enter**:

```powershell
Set-Content -Path .env -Value "BEDTRACKER_SIMPLE_LOGIN=true" -Encoding utf8
```

Nothing visible happens — that is normal. It created a small settings file
called `.env` that switches the app into "name only" login mode.

*(To check it worked, type `type .env` and press Enter — it should print
`BEDTRACKER_SIMPLE_LOGIN=true`.)*

---

## Part 3 — Refresh the demo data (optional)

This wipes the practice patients and puts back a fresh set. Skip it if you
don't need a clean slate.

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo --reset
```

It prints a few lines ending in `Done.`

---

## Part 4 — Start the app

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

After a moment you'll see:

```
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

**Leave this window open.** The app is now running.

---

## Part 5 — Use it

- Open a web browser and go to: **http://localhost:8000**
- You'll see the **Enter your name to continue** screen.
- Type a name, click **Enter Ward Board**. That's it.
- Each tester does the same on their own device/browser with their own name.
  Their name shows up in the History and Ward Activity records.

---

## Part 6 — Stop the app

Click the PowerShell window, then press **Ctrl** + **C**.
You get the `...BedTracker>` prompt back. You can close the window.

To start it again another day: do **Part 1** and **Part 4** only
(Parts 2 and 3 are one-time).

---

## Switching back to real email + password login

When testing is done:

```powershell
Remove-Item .env
```

Then start the app again (Part 4). The login page is back to email + password
and signup. Nothing else changes — any accounts and data are kept.

---

## If something goes wrong

| Message | What to do |
|---|---|
| `That port is already in use` | The app is already running in another PowerShell window — use that one, or close it and try again. Or run `.\.venv\Scripts\python.exe manage.py runserver 8001` and use **http://localhost:8001** |
| `cannot be loaded because running scripts is disabled` | You typed an `Activate` command — don't. Always use the full `.\.venv\Scripts\python.exe ...` form shown above. |
| `No such file or directory: manage.py` | Your window isn't in the right folder. Redo **Part 1**. |
| Browser says "can't reach this page" | The `runserver` window was closed or Ctrl+C'd. Redo **Part 4**. |

---

## Letting other testers on the same Wi-Fi connect

By default only this computer can open the app. To let phones/laptops on the
same network in:

1. Start it with:
   `.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000`
2. Find this PC's address: run `ipconfig`, look for **IPv4 Address**
   (e.g. `192.168.1.20`).
3. Testers open `http://192.168.1.20:8000` in their browser.
4. The first time, Windows may pop up a firewall box — click **Allow access**
   for private networks.
