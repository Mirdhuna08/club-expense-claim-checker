
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import re

app = Flask(__name__)

DATABASE = "expense_claims.db"

# Budget for each club
club_budgets = {
    "Coding Club": 10000,
    "Music Club": 8000,
    "Robotics Club": 15000
}


# Connect to the database
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# Create the database table
def initialize_database():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            bill_available INTEGER NOT NULL,
            status TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# Extract expense amount
def extract_amount(claim):
    match = re.search(
        r'(?:Rs\.?|₹)\s*([\d,]+(?:\.\d{1,2})?)',
        claim,
        re.IGNORECASE
    )

    if match:
        return float(match.group(1).replace(",", ""))

    return None


# Find expense category
def extract_category(claim):
    claim = claim.lower()

    categories = {
        "Stationery": ["pen", "pencil", "notebook", "paper"],
        "Food": ["food", "snacks", "lunch", "refreshments"],
        "Printing": ["printing", "print", "photocopy", "banner"],
        "Travel": ["travel", "taxi", "bus", "train"],
        "Equipment": ["laptop", "projector", "computer"]
    }

    for category, keywords in categories.items():
        if any(word in claim for word in keywords):
            return category

    return "Other"


# Check whether a bill is attached
def check_bill(claim):
    claim = claim.lower()

    bill_words = [
        "bill attached",
        "receipt attached",
        "invoice attached"
    ]

    return any(word in claim for word in bill_words)


# Calculate club spending
def get_club_spending(club):
    conn = get_db_connection()

    approved = conn.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM claims
        WHERE club = ? AND status = 'Approved'
    """, (club,)).fetchone()[0]

    pending = conn.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM claims
        WHERE club = ? AND status = 'Pending Approval'
    """, (club,)).fetchone()[0]

    conn.close()

    return approved, pending


# Save expense claim
def save_claim(club, description, amount, category, bill, status):
    conn = get_db_connection()

    conn.execute("""
        INSERT INTO claims
        (club, description, amount, category, bill_available, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        club,
        description,
        amount,
        category,
        int(bill),
        status
    ))

    conn.commit()
    conn.close()


# Home page and claim submission
@app.route("/", methods=["GET", "POST"])
def home():

    if request.method == "POST":

        claim = request.form.get("claim", "").strip()
        club = request.form.get("club", "")

        if not claim:
            message = "Please enter an expense claim."

        elif club not in club_budgets:
            message = "Please select a valid club."

        else:
            amount = extract_amount(claim)
            category = extract_category(claim)
            bill = check_bill(claim)

            if amount is None or amount <= 0:
                message = "Please enter a valid amount."

            elif not bill:
                save_claim(
                    club, claim, amount, category,
                    bill, "Needs a bill"
                )
                message = "Bill is required. Claim recorded."

            else:
                approved, pending = get_club_spending(club)

                available = club_budgets[club] - approved - pending

                if amount > available:
                    save_claim(
                        club, claim, amount, category,
                        bill, "Over budget"
                    )
                    message = "Claim is over budget."

                else:
                    save_claim(
                        club, claim, amount, category,
                        bill, "Pending Approval"
                    )
                    message = "Claim submitted successfully."

        return redirect(url_for("dashboard", message=message))

    return redirect(url_for("dashboard"))


# Dashboard page
@app.route("/dashboard")
def dashboard():

    message = request.args.get("message", "")

    conn = get_db_connection()

    claims = conn.execute(
        "SELECT * FROM claims ORDER BY id DESC"
    ).fetchall()

    conn.close()

    budget_details = {}

    for club, budget in club_budgets.items():

        approved, pending = get_club_spending(club)

        budget_details[club] = {
            "budget": budget,
            "approved": approved,
            "pending": pending,
            "remaining": budget - approved - pending
        }

    return render_template(
        "index.html",
        result=message,
        claims=claims,
        clubs=club_budgets,
        budget_details=budget_details
    )


# Approve a claim
@app.route("/approve/<int:claim_id>", methods=["POST"])
def approve_claim(claim_id):

    conn = get_db_connection()

    claim = conn.execute(
        "SELECT * FROM claims WHERE id = ?",
        (claim_id,)
    ).fetchone()

    if claim and claim["status"] == "Pending Approval":

        approved, pending = get_club_spending(claim["club"])

        budget = club_budgets[claim["club"]]

        if approved + claim["amount"] <= budget:
            conn.execute("""
                UPDATE claims
                SET status = 'Approved'
                WHERE id = ?
            """, (claim_id,))

            conn.commit()

    conn.close()

    return redirect(url_for("dashboard"))


# Reject a claim
@app.route("/reject/<int:claim_id>", methods=["POST"])
def reject_claim(claim_id):

    conn = get_db_connection()

    conn.execute("""
        UPDATE claims
        SET status = 'Rejected'
        WHERE id = ? AND status = 'Pending Approval'
    """, (claim_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


initialize_database()

if __name__ == "__main__":
    app.run(debug=False)
    
