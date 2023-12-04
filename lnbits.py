import json

import requests
from tenacity import RetryError, stop_after_attempt, AsyncRetrying
from dotenv import load_dotenv
from tenacity import wait_exponential
import asyncio
import httpx
import os

load_dotenv()

headers = {
    "X-Api-Key": os.environ["lnbits_invoice_key"],
    "Content-type": "application/json",
}
admin_header = {
    "X-Api-Key": os.environ["lnbits_admin_key"],
    "Content-type": "application/json",
}
lnbits_host = str(os.environ["lnbits_host"])


async def create_invoice(message: str):
    """print log are good to see what the script is doing in case of bugs the following can may result difficult to
    read for you but is tenacity and it retry 3 times the api call, in case of timeout """
    print("creating invoice: " + message)
    try:
        async for attempt in AsyncRetrying(
                wait=wait_exponential(multiplier=1, min=4, max=30),
                stop=stop_after_attempt(3),
        ):
            with attempt:
                async with httpx.AsyncClient() as client:
                    data = {"out": 'false', "amount": 500, "memo": "LightningLottery " + message, "unit": "sat"}
                    response = await client.post(
                        lnbits_host + "/api/v1/payments",
                        headers=headers,
                        data=data,
                    )
                    # timeout = 120 (not used)
                    payment_data = response.json()
                    print("invoice created and returned to pyrogram!")
                    return payment_data

    except RetryError:
        print("failed to create an invoice")
        return None


async def verify_invoice(payment_hash, invoice_verified=False, countdown=120):
    print("invoice verification started")
    while not invoice_verified and countdown > 0:
        await asyncio.sleep(3)
        countdown -= 3
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    lnbits_host + "/api/v1/payments/" + payment_hash,
                    headers=headers,
                )
                timeout = 120
                payment_status = response.json()
                if payment_status['paid'] is False:
                    continue
                elif payment_status['paid']:  # explicitly check for true payment status in case of weird response
                    print("invoice verified successfully (stonks)!")
                    invoice_verified = True
                    return True
        except Exception as e:
            print(e)
    if not invoice_verified:
        return False


async def get_balance():
    try:
        async for attempt in AsyncRetrying(
                wait=wait_exponential(multiplier=1, min=4, max=30),
                stop=stop_after_attempt(3),
        ):
            with attempt:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        lnbits_host + "/api/v1/wallet",
                        headers=headers)
                    return int(response.json()["balance"])
    except RetryError:
        print("failed to fetch balance")
        return None


async def payout(lnaddress: str, amount: int):
    try:
        async for attempt in AsyncRetrying(
                wait=wait_exponential(multiplier=1, min=4, max=30),
                stop=stop_after_attempt(3),
        ):
            with attempt:
                async with httpx.AsyncClient() as client:
                    lnaddress = lnaddress.replace("@", "%40")
                    response = await client.get(
                        lnbits_host + "/api/v1/lnurlscan/" + lnaddress,
                        headers=headers)
                    response = response.json()
                    payment_form = json.dumps({
                        "description_hash": response["description_hash"],
                        "callback": response["callback"],
                        "amount": amount * 1000,
                        "comment": "Lottery payout!",
                        "description": "Lottery payout"
                    })
                    payment = await client.post(lnbits_host + "/api/v1/payments/lnurl", headers=admin_header,
                                                data=payment_form)
                    return payment.json()["payment_hash"]
    except RetryError:
        print("failed to payout to ln address")
        return None