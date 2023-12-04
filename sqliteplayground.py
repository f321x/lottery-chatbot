# this is only for testing and playing around

import sqlite3
from random import randint, sample
from time import time

db = sqlite3.connect("lottery.db")
db_cursor = db.cursor()

db_cursor.execute(
    "CREATE TABLE IF NOT EXISTS lottery_numbers (id INTEGER PRIMARY KEY, time TEXT, numbers TEXT)")
db_cursor.execute(
    "CREATE TABLE IF NOT EXISTS user_numbers (id INTEGER PRIMARY KEY,user_id TEXT, numbers TEXT)")
db_cursor.execute(
    "CREATE TABLE IF NOT EXISTS user_lnaddress (id INTEGER PRIMARY KEY, user_id TEXT, lnaddress TEXT)")


def extract_lottery_numbers():
    ln = sample(range(1, 50), 6)
    db_cursor.execute(
        "INSERT INTO lottery_numbers (time, number1, number2, number3, number4, number5, number6) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (int(time()), ln[0], ln[1], ln[2], ln[3], ln[4], ln[5]))
    db.commit()
    return set(map(str, ln))


def get_winner(winning_users=None, max_match_count=0):
    db_cursor.execute("SELECT * FROM user_numbers")
    user_numbers = db_cursor.fetchall()

    # compare user numbers with random lottery result and return the user from db with the most common numbers
    # if no user has at least one common number with the result, try again
    while winning_users is None:
        ln = set(map(str, sample(range(1, 50), 6)))
        print("ln: " + str(ln))
        for row in user_numbers:
            un_list = set(row[2].split(","))
            # Convert the user_number to a set and find the number of matching elements
            match_count = len(ln.intersection(un_list))
            # Update the winning tuple and max_match_count if necessary
            print("max: " + str(max_match_count))
            if match_count > max_match_count:
                max_match_count = match_count
                winning_users = [row]
            elif match_count == max_match_count and max_match_count > 0:
                winning_users.append(row)

    # documentation of the winning number in case of problems, etc...
    # db_cursor.execute("INSERT INTO lottery_numbers (time, numbers) VALUES (?, ?)", (int(time()), ",".join(ln)))
    # db.commit()

    # return the db row of the winner with the most common numbers of the random lottery result
    # this can be passed to payout function and tg notification function
    # after successfull payout we can drop the user database
    return winning_users


def simulate_user():
    for n in range(1500):
        # text = f"{randint(1, 50)},{randint(1, 50)},{randint(1, 50)},{randint(1, 50)},{randint(1, 50)},{randint(1, 50)}"
        lnaddress = f"{randint(50000,500000)}@{randint(50000,5000000)}.com"
        db_cursor.execute("INSERT INTO user_lnaddress (user_id, lnaddress) VALUES (?, ?)",
                          (randint(1001, 9999), lnaddress))
        db.commit()


#print(get_winner())
# simulate_user()
# for number in list:
#     print(len(set('10,15,41,26,25,17'.split(",")).intersection(set(number[2].split(",")))))

# db_cursor.execute("SELECT * FROM user_numbers")
# user_numbers = db_cursor.fetchone()

# print(user_numbers)

db_cursor.execute("SELECT lnaddress FROM user_lnaddress WHERE user_id=?", ("8251",))
lnaddress = db_cursor.fetchone()[0]
print(lnaddress)