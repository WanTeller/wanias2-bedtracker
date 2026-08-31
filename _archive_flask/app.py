"""
BedTracker - v1 (simplest version)

What this file is:
  A tiny web server. When someone opens the page in a browser, this program
  builds the HTML for that page and sends it back. When someone clicks a
  button to change a bed's status, this program updates the saved data.

The three "pieces" in this file:
  1. Setup        - import tools, create the app, point at the database file
  2. Database     - a function to open the database + a function to create it
  3. Pages        - "routes": which web address does what
"""

# ----------------------------------------------------------------------------
# 1. SETUP
# ----------------------------------------------------------------------------

# Flask is the library that turns Python into a web server.
# - Flask:            the app itself
# - render_template:  loads an HTML file from the "templates" folder and fills
#                     in the blanks with data we give it
# - request:          holds whatever the browser sent us (e.g. form fields)
# - redirect/url_for: send the browser to a different page after an action
from flask import Flask, render_template, request, redirect, url_for

# sqlite3 comes built into Python. SQLite is a database that lives in a single
# file on disk (here: "beds.db"). No separate database program to install.
import sqlite3

# Create the application object. __name__ just tells Flask where it lives.
app = Flask(__name__)

# The name of our database file. It will be created next to this script.
DB = "beds.db"

# The only statuses a bed is allowed to have. Keeping this list in one place
# means the dropdown on the page and the validation below can never disagree.
STATUSES = ["Available", "Occupied", "Cleaning"]


# ----------------------------------------------------------------------------
# 2. DATABASE
# ----------------------------------------------------------------------------

def get_db():
    """Open a connection to the database file and return it.

    row_factory = sqlite3.Row lets us read columns by name later
    (bed["ward"]) instead of by number (bed[1]), which is easier to read.
    """
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the 'beds' table if it doesn't exist yet, and add a few
    sample beds the first time so the page isn't empty.

    Runs every startup, but 'IF NOT EXISTS' + the count check make it safe
    to run repeatedly - it won't wipe or duplicate anything.
    """
    conn = get_db()

    # A table is like one sheet in a spreadsheet. Columns:
    #   id     - a unique number per bed, assigned automatically
    #   ward   - e.g. "Ward A"
    #   room   - e.g. "101"
    #   label  - the bed's name/tag, e.g. "A-101-1"
    #   status - one of STATUSES, starts as "Available"
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS beds (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            ward   TEXT NOT NULL,
            room   TEXT NOT NULL,
            label  TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Available'
        )
        """
    )

    # Only seed sample data if the table is currently empty.
    already_there = conn.execute("SELECT COUNT(*) FROM beds").fetchone()[0]
    if already_there == 0:
        sample_beds = [
            ("Ward A", "101", "A-101-1"),
            ("Ward A", "101", "A-101-2"),
            ("Ward A", "102", "A-102-1"),
            ("Ward B", "201", "B-201-1"),
            ("Ward B", "202", "B-202-1"),
        ]
        # executemany runs the same INSERT once per row in the list.
        # The "?" are placeholders - sqlite fills them in safely. Never build
        # SQL by gluing strings together; that's how databases get hacked.
        conn.executemany(
            "INSERT INTO beds (ward, room, label) VALUES (?, ?, ?)",
            sample_beds,
        )

    conn.commit()   # save changes
    conn.close()    # let go of the file


# ----------------------------------------------------------------------------
# 3. PAGES (routes)
# ----------------------------------------------------------------------------

@app.route("/")
def index():
    """The main page: show every bed and its status.

    '@app.route("/")' means: when the browser asks for the site root
    (e.g. http://localhost:5000/ ), run this function.
    """
    conn = get_db()
    beds = conn.execute(
        "SELECT * FROM beds ORDER BY ward, room, label"
    ).fetchall()
    conn.close()

    # Hand the data to the HTML template. Inside index.html we can now loop
    # over 'beds' and read 'statuses'.
    return render_template("index.html", beds=beds, statuses=STATUSES)


@app.route("/update/<int:bed_id>", methods=["POST"])
def update(bed_id):
    """Change one bed's status.

    The <int:bed_id> part of the address is a variable: /update/3 means
    bed_id = 3. methods=["POST"] means this only responds to form
    submissions, not to someone just visiting the URL.
    """
    new_status = request.form["status"]   # what the dropdown was set to

    # Only accept a status from our known list. Ignore anything else.
    if new_status in STATUSES:
        conn = get_db()
        conn.execute(
            "UPDATE beds SET status = ? WHERE id = ?",
            (new_status, bed_id),
        )
        conn.commit()
        conn.close()

    # Send the browser back to the main page so it reloads with the change.
    return redirect(url_for("index"))


# ----------------------------------------------------------------------------
# START THE SERVER
# ----------------------------------------------------------------------------

# This block only runs when you do "python app.py" directly.
if __name__ == "__main__":
    init_db()   # make sure the table + sample data exist

    # host="0.0.0.0" -> other computers on your network can reach it, not just
    #                   this machine. They'd visit http://<your-ip>:5000
    # port=5000     -> the "door number" the server listens on
    # debug=True    -> auto-reloads when you edit this file, and shows detailed
    #                  errors. Turn this OFF if this is ever exposed publicly.
    app.run(host="0.0.0.0", port=5000, debug=True)
