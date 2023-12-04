from convopyro import Conversation, listen_message
from lnbits import create_invoice, verify_invoice, payout, get_balance
from pyrogram import Client, filters
from dotenv import load_dotenv
import random
import os
import time
import pyqrcode
import sqlite3
import logging
from crontab import CronTab
import argparse
import asyncio

# import tweepy #later I'll do a Twitter bot that post every week the numbers

# setup logging
logging.basicConfig(
    filename="log.txt",
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# load environment variables from .env file
load_dotenv()

# import random SystemRandom class for better randomness
rng = random.SystemRandom()


# initialize cronjob
def create_cronjob():
    with CronTab(user=os.getlogin()) as cron:
        cronjob_exists = False
        for cronjob in cron:
            if str(cronjob)[-13:] == 'LotteryPayout':
                logging.info("Cronjob already exists, not created.")
                cronjob_exists = True
        if not cronjob_exists:
            job = cron.new(command='python3 main.py extract', comment='LotteryPayout')
            job.hour.every(10)
            logging.info("Cronjob created, IMPORTANT check if correct in cronfile")
            print("Cronjob created!")


# initialize pyrogram with env variables from .env file
tg = Client(
    "lottery_bot",
    api_id=int(os.environ["tg_api_id"]),
    api_hash=str(os.environ["tg_api_hash"]),
    bot_token=str(os.environ["tg_bot_token"]),
)
Conversation(tg)

# connect to sqlite db
db = sqlite3.connect("lottery.db")
db_cursor = db.cursor()

# create tables if they don't exist
db_cursor.execute(
    "CREATE TABLE IF NOT EXISTS lottery_numbers (id INTEGER PRIMARY KEY, time TEXT, numbers TEXT)")
db_cursor.execute(
    "CREATE TABLE IF NOT EXISTS user_numbers (id INTEGER PRIMARY KEY, user_id TEXT, numbers TEXT)")
db_cursor.execute(
    "CREATE TABLE IF NOT EXISTS user_archive (id INTEGER PRIMARY KEY, user_id TEXT, numbers TEXT)")
db_cursor.execute(
    "CREATE TABLE IF NOT EXISTS user_lnaddress (id INTEGER PRIMARY KEY, user_id TEXT, lnaddress TEXT)")

# message to do not consider as answer
skip_message = ["/start", "/faq", "/help, /register", "/support", "/change"]


def get_winners(winning_users=None, max_match_count=0):
    db_cursor.execute("SELECT * FROM user_numbers")
    user_numbers = db_cursor.fetchall()
    if user_numbers:
        while not winning_users:
            try:
                ln = set(map(str, rng.sample(range(1, 50), 6)))
            except NotImplementedError:
                ln = set(map(str, random.sample(range(1, 50), 6)))
                logging.error("OS doesn't provide good randomness source")
            for row in user_numbers:
                un_list = set(row[2].split(","))
                match_count = len(ln.intersection(un_list))
                if match_count > max_match_count:
                    max_match_count = match_count
                    winning_users = [row]
                elif match_count == max_match_count and max_match_count > 0:
                    winning_users.append(row)
        # documentation
        db_cursor.execute("INSERT INTO lottery_numbers (time, numbers) VALUES (?, ?)", (int(time.time()), ",".join(ln)))
        db.commit()
        return [winning_users, max_match_count, user_numbers, str(",".join(ln))]
    else:
        logging.info("get_winners returns None, no winners as no users registered for the lottery")
        return None


async def payout_winners():  # run this func as cron job every week
    winners = get_winners()
    if winners is not None:
        lnbits_balance = int(int(await get_balance()) * 0.99)  # we should let some reserves on lnbits for routing fees
        prize_per_winner = int((lnbits_balance * 0.9) / len(winners[0]))
        for winner in winners[0]:
            # get the lnaddress of the winner from the payment data db
            db_cursor.execute("SELECT lnaddress FROM user_lnaddress WHERE user_id=?", (winner[1],))
            lnaddress = db_cursor.fetchone()[0]
            # payout to lnaddress
            if payout(lnaddress, prize_per_winner):
                # notify winner
                await tg.send_message(winner[1], f"Congrats you won the lottery. {prize_per_winner} "
                                                 f"sats have been paid to your lightning address: {lnaddress} ")
                logging.info(f'{winner}, has been paid {prize_per_winner} sats')
            elif payout is None:
                await tg.send_message(winner[1],
                                      f"You won the lottery but the lightning payout to {lnaddress} failed \n"
                                      f"please press /support and provide us with payment information"
                                      f" (bolt11 or onchain) to pay you your prize.")
                logging.error(f'Payout to tg user {winner} failed, payout manually.')

        # payout to us, well deserved :D
        await payout("lnaddress1", int(lnbits_balance * 0.05))
        await payout("lnaddress2", int(lnbits_balance * 0.05))

        for user in winners[2]:
            if user not in winners[0]:
                await tg.send_message(user[1], f"{prize_per_winner} sats have been paid out to {len(winners)}"
                                               f" participants who all guessed {winners[1]} numbers of the"
                                               f"winning set '{winners[3]}'. The next lottery week is starting now."
                                               f"You can take part again in the next draw with\n/register")
        # clean user db and move data to archive db for documentation
        db_cursor.execute("INSERT INTO user_archive SELECT * FROM user_numbers")
        db_cursor.execute("DELETE FROM user_numbers")
        db.commit()
        logging.info("Winners paid out, user db archived")
    else:
        print("No users/winners, no payout, do more advertising")
        logging.info("payout_winners pays nobody due to None from get_winners")


# bot commands after this, before bot function (not commands)

@tg.on_message(filters.command("start"))
async def support(client, message):
    await tg.send_message(
        message.chat.id,
        f"Welcome in the lottery bot!\nWe do an automatic weekly extraction of 6 numbers, pick your numbers, "
        f"deposit with LN and good luck!\n"
        f"To learn more about this lottery press /info otherwise,\nto get started press /register",
    )
    return


@tg.on_message(filters.command("support"))
async def support(client, message):
    await tg.send_message(
        message.chat.id,
        f"For any support request feel free to contact: @lotterybotsupport",  # to be created
    )


@tg.on_message(filters.command("register"))
async def register(client, message):
    db_cursor.execute("SELECT lnaddress FROM user_lnaddress WHERE user_id=?", (message.chat.id,))
    lnaddress = db_cursor.fetchone()[0]
    if lnaddress:
        await tg.send_message(
            message.chat.id,
            f"Here we go! Send me 6 numbers between 1 and 50 and separate with a comma.\nExample: 22,11,"
            f"4,6,4,50 ")
        numbers_valid = False
        while not numbers_valid:
            numbers = await listen_message(client, message.chat.id, timeout=None)
            if numbers.text in skip_message:
                return
            elif numbers.text and len(numbers.text.split(",")) == 6:
                payment_data = await create_invoice(str(numbers.text))
                if payment_data is not None:
                    qrcode = pyqrcode.create(payment_data['payment_request'])
                    qrcode.png("invoice.png", scale=5)
                    await message.reply_photo(
                        "invoice.png",  # before launch, we need to import and use uuid for files.
                        message.chat.id,
                        caption=f"<code>{payment_data['payment_request']}</code>"
                                + "\nPlease pay the invoice to continue!\nThe invoice will expire in 2 minutes.",
                    )
                    # now check for payment here
                    invoice_status = await verify_invoice(payment_data['payment_hash'])
                    if invoice_status is True:
                        numbers = message.text.split(",")
                        db_cursor.execute("INSERT INTO user_numbers (user_id, numbers) VALUES (?, ?)",
                                          (message.from_user.id, ",".join(numbers)))
                        db.commit()
                        await tg.send_message(message.chat.id,
                                              "Your numbers have been registered. You will be notified "
                                              "of the winning numbers. Good luck!")
                        logging.info("user registered successfully")
                        break
                    else:
                        await tg.send_message(message.chat.id, "You haven't paid your invoice in 2 minutes so it has "
                                                               "timed out, if you want to try again press "
                                                               "on\nregister\nagain.")
                        break
                else:
                    await tg.send_message(
                        message.chat.id,
                        "Internal server error. Try again later or contact or press\n/support")
                    logging.error("Problem with registration, invoice creation returned None")
    else:
        await tg.send_message(message.chat.id, f'First you need to register a lightning address for the automatic'
                                               f'payout of the prizes you win. A lightning address has the format '
                                               f'"example@example.com".\nPlease send your lightning address below:')
        lnaddress_valid = False
        while not lnaddress_valid:
            user_lnaddress = await listen_message(client, message.chat.id, timeout=None)
            if user_lnaddress.text in skip_message:
                break
            elif '@' in user_lnaddress.text and '.' in user_lnaddress.text:
                db_cursor.execute("INSERT INTO user_lnaddress (user_id, lnaddress) VALUES (?,?)", (message.chat.id,
                                                                                                   user_lnaddress.text))
                db.commit()
                await tg.send_message(message.chat.id, f'Your payout address {user_lnaddress.text} has been saved.\n'
                                                       f'You can change the address by sending /change'
                                                       f'Press /register again to enter the lottery.')
                break
            else:
                await tg.send_message(message.chat.id, f'The text you entered is not a valid lightning address. '
                                                       f'Try again.')


@tg.on_message(filters.command("change"))
async def change(client, message):
    db_cursor.execute("SELECT lnaddress FROM user_lnaddress WHERE user_id=?", (message.chat.id,))
    lnaddress = db_cursor.fetchone()[0]
    if lnaddress:
        await tg.send_message(message.chat.id, f'Your current payout address is\n{lnaddress}\n'
                                               f'You now can enter your new one below or exit with /register :')
        lnaddress = False
        while not lnaddress:
            user_lnaddress = await listen_message(client, message.chat.id, timeout=None)
            if user_lnaddress.text in skip_message:
                break
            elif '@' in user_lnaddress.text and '.' in user_lnaddress.text:
                db_cursor.execute("DELETE FROM user_lnaddress WHERE user_id=?", (message.chat.id,))
                db_cursor.execute("INSERT INTO user_lnaddress (user_id, lnaddress) VALUES (?,?)", (message.chat.id,
                                                                                                   user_lnaddress.text))
                db.commit()
                await tg.send_message(message.chat.id,
                                      f'Your payout address has been updated to {user_lnaddress.text}.\n'
                                      f'You can change the address again by sending /change\n'
                                      f'Press /register to enter the lottery.')
                break
            else:
                await tg.send_message(message.chat.id, f'The text you entered is not a valid lightning address. '
                                                       f'Try again.')
    else:
        await tg.send_message(message.chat.id, f"You haven't saved a payout lightning address yet, press\n/register\n"
                                               f"to get started.")


@tg.on_message(filters.command("help"))
async def help1(client, message):
    await tg.send_message(
        message.chat.id,
        f"If you encounter any problems please check the /faq or have a look in the lottery bot Telegram group.\n"
        f"If you need support or found a bug/problem please press /support.\n Otherwise, good luck!",
    )


@tg.on_message(filters.command("faq"))
async def faq(client, message):
    await tg.send_message(
        message.chat.id,
        f"Here are some frequently asked questions: \n"
        f"nothing here yet \n"
        f"If this didn't help, you can press /support",
    )


@tg.on_message(filters.command("info"))
async def info(client, message):
    await tg.send_message(
        message.chat.id,
        f"This bot will do a weekly draw of the winning numbers and automatically payout the winners to their "
        f"registered lightning address.\n "
        f"All users who took part in the lottery will be informed of the winning numbers and payout sums."
        f"Of all satoshis paid to the bot 90% will be paid out to the winners and 10% will go to the maintainers."
        # ...
    )


# echo to handle users who just type something in without the right prompt
@tg.on_message(filters.text)
async def echo(client, message):
    await tg.send_message(message.chat.id, f"Press /register to get started.")


# run the program
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='A Telegram lottery bot')
    subparsers = parser.add_subparsers(dest='command')
    bot_parser = subparsers.add_parser('bot', help='run the Telegram chatbot')
    extract_parser = subparsers.add_parser('extract', help='argument to run the extraction, for the cron scheduler')
    args = parser.parse_args()
    if args.command == 'bot':
        print("Starting the Telegram bot...")
        create_cronjob()
        tg.run()
    if args.command == 'extract':  # doesn't need to be run, just for the cronjob execution
        print("Running the extraction...")
        asyncio.run(payout_winners())
