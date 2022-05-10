import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, date

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Create table to track all orders made on site
db.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER NOT NULL, user_id NUMERIC NOT NULL, symbol TEXT NOT NULL, \
            shares NUMERIC NOT NULL, order_type TEXT NOT NULL, price NUMERIC NOT NULL, time NUMERIC NOT NULL, PRIMARY KEY(id), \
            FOREIGN KEY(user_id) REFERENCES users(id))")

# Create table to keep track of portfolios
db.execute("CREATE TABLE IF NOT EXISTS positions (user_id NUMERIC NOT NULL, symbol TEXT NOT NULL, \
            shares NUMERIC NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))")

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Query database for users stocks and add them all to a list
    positions = db.execute("SELECT symbol, shares FROM positions WHERE user_id = ?", session["user_id"])
    symbols = []
    shares = []
    prices = []
    values = []
    total_value = 0

    for i in positions:
        symbols.append(i["symbol"])
        shares.append(i["shares"])
        price = lookup(i["symbol"])["price"]
        values.append(usd(price * i["shares"]))
        total_value += price * i["shares"]
        price = usd(price)
        prices.append(price)

    # Combine lists to make one itterable and compute account balances
    portfolio = zip(symbols, shares, prices, values)
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    balance = cash[0]["cash"]
    total_value += balance
    balance = usd(balance)
    total_value = usd(total_value)

    return render_template("home.html", portfolio=portfolio, total_value=total_value, balance=balance)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # Check if share are positive int, exists, and is valid
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("Stock does not exist")

        if not request.form.get("shares").isdigit():
            return apology("You cannot buy fractional shares")

        if int(request.form.get("shares")) < 1:
            return apology("Must buy at least 1 share")

        stock = lookup(request.form.get("symbol").strip())
        if not stock:
            return apology("Stock does not exist")

        price = stock["price"]
        symbol = stock["symbol"].upper()
        shares = int(request.form.get("shares"))
        user_id = session["user_id"]
        current_cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
        balance = current_cash - (price * shares)

        if balance < 0:
            return apology("Insufficient funds")

        # Check if user already owns shares of this stock, if so add to that position, otherwise insert a new position into table
        check = db.execute("SELECT symbol FROM positions WHERE symbol = ? AND user_id = ?", symbol, user_id)
        if len(check) == 1:
            total = db.execute("SELECT shares FROM positions WHERE symbol = ? AND user_id = ?", symbol, user_id)
            total_shares = total[0]["shares"] + shares
            db.execute("UPDATE positions SET shares = ? WHERE user_id = ? AND symbol = ?", total_shares, user_id, symbol)
        else:
            db.execute("INSERT INTO positions (user_id, symbol, shares) VALUES(?, ?, ?)", user_id, symbol, shares)

        # Update user cash and add order to order table
        db.execute("UPDATE users SET cash = ? WHERE id=?", balance, user_id)
        db.execute("INSERT INTO orders (user_id, symbol, shares, order_type, price, time) VALUES(?, ?, ?, ?, ?, ?)", user_id, symbol, shares, "buy", price, str(date.today()) + " " + str(datetime.now().strftime("%H:%M:%S")))

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Query orders table and select rows where user id matches that row, then render said table
    history = db.execute("SELECT symbol, shares, order_type, price, time FROM orders WHERE user_id = ?", session["user_id"])
    for i in history:
        i["price"] = usd(i["price"])

    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # Check if valid inpit then render that stocks price
    if request.method == "POST":

        if not request.form.get("symbol") or not lookup(request.form.get("symbol").strip()):
            return apology("Stock does not exist")

        stock = lookup(request.form.get("symbol").strip())
        stock["price"] = usd(stock["price"])
        return render_template("quoted.html", stocks=stock)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Check for valid input, matching passwords, and duplicate username
    if request.method == "POST":

        if not request.form.get("username"):
            return apology("must provide username")

        elif not request.form.get("password"):
            return apology("must provide password")

        user = db.execute("SELECT username FROM users WHERE username = ?", request.form.get("username"))
        if len(user) != 0:
            return apology("Username already in use")

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match")

        username = request.form.get("username")
        hash = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hash)
        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Check if valid input
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("Stock does not exist")

        if not request.form.get("shares"):
            return apology("Did not enter share amount")

        if not request.form.get("shares").isdigit():
            return apology("You cannot buy fractional shares")

        if int(request.form.get("shares")) < 1:
            return apology("Must sell at least 1 share")

        stock = lookup(request.form.get("symbol").strip())
        symbol = stock["symbol"]
        price = stock["price"]
        portfolio = db.execute("SELECT symbol, shares FROM positions WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)

        if len(portfolio) == 0:
            return apology("you do not own any of this stock")

        shares = int(request.form.get("shares"))
        if shares > portfolio[0]["shares"]:
            return apology("you do not own enough shares to sell this amount")

        # Add transaction to orders table
        sale = price * shares
        db.execute("UPDATE users SET cash = (cash + ?) WHERE id = ?", sale, session["user_id"])
        db.execute("INSERT INTO orders (user_id, symbol, shares, order_type, price, time) VALUES(?, ?, ?, ?, ?, ?)", session["user_id"], symbol, shares, "sell", price, str(date.today()) + " " + str(datetime.now().strftime("%H:%M:%S")))

        # If transaction results in user having 0 shares of a stock, remove that position from the table, otherwise update that position instead
        if shares - portfolio[0]["shares"] == 0:
            db.execute("DELETE FROM positions WHERE symbol = ? AND user_id = ?", symbol, session["user_id"])

        else:
            db.execute("UPDATE positions SET shares = (shares - ?) WHERE user_id = ? AND symbol = ?", shares, session["user_id"], symbol)

        return redirect("/")

    stocks = db.execute("SELECT symbol FROM positions WHERE user_id = ?", session["user_id"])

    return render_template("sell.html", stocks=stocks)


@app.route("/add-cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """Add cash to account"""

    # Check if valid input
    if request.method == "POST":

        input = float(request.form.get("cash").strip())

        if not input:
            return apology("No input")

        if input <= 0:
            return apology("Amount must be more than 0")

        # Update users table with new cash amount for user
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", input, session["user_id"])

        return redirect("/")

    return render_template("add-cash.html")
