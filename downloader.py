import requests
import os
import random

from time import sleep
from datetime import datetime, timedelta

OCTOPUS_USERNAME = os.getenv("OCTOPUS_USERNAME")
OCTOPUS_PASSWORD = os.getenv("OCTOPUS_PASSWORD")
BILL_COUNT = int(os.getenv("BILL_COUNT", "1"))
DOWNLOAD_ONCE = int(os.getenv("DOWNLOAD_ONCE", "1"))
SAVE_LOCATION = os.getenv("SAVE_LOCATION", ".")
DOWNLOAD_TIME = os.getenv(
    "DOWNLOAD_TIME", f"{random.randint(0, 23):02}:{random.randint(1, 59):02}"
)

AUTORUN = ":" in DOWNLOAD_TIME

print("INFO: Octopus Energy Bill Downloader (OEBD)")
print("INFO: Runtime:", DOWNLOAD_TIME if AUTORUN else "ONCE")

endpoint = f"https://api.octopus.energy/v1/graphql/"


def run_query(
    query, variables: dict = {}, with_auth: bool = True, force_auth: bool = False
):
    headers = (
        {"Authorization": f"JWT {get_jwt(force=force_auth)}"}
        if with_auth or force_auth
        else {}
    )
    r = requests.post(
        endpoint, json={"query": query, "variables": variables}, headers=headers
    )
    if r.status_code == 200:
        return r.json() if r.text and r.text.startswith("{") else {}
    else:
        raise Exception(f"ERROR: non-200 response: {r.status_code}")


_jwt = None


def get_jwt(force: bool = False):
    global _jwt
    if not _jwt or force:
        _jwt = (
            run_query(
                """
                mutation krakenTokenAuthentication($email: String!, $password: String!) {
                    obtainKrakenToken(input: {email: $email, password: $password}) {
                        token
                    }
                }
                """,
                {"email": OCTOPUS_USERNAME, "password": OCTOPUS_PASSWORD},
                with_auth=False,
            )
            .get("data", {})
            .get("obtainKrakenToken", {})
            .get("token", None)
        )
        if _jwt:
            print("INFO: Successfully signed in and acquired authentication token")
        else:
            raise Exception(f"ERROR: sign in or token acquisition failed")
    return _jwt


def get_accounts():
    return (
        run_query(
            """
            query get_accounts {
                viewer {
                    accounts {
                        brand
                        number
                        status
                        billingAddress
                        billingAddressLine1
                        billingAddressLine2
                        billingAddressLine3
                        billingAddressLine4
                        billingAddressLine5
                        billingAddressPostcode
                        billingCountryCode
                        accountType
                    }
                }
            }
            """,
            force_auth=True,
        )
        .get("data", {})
        .get("viewer", {})
        .get("accounts", [])
    )


def get_bills(account_number: str, count: int = 12):
    if not account_number:
        return {}

    return (
        run_query(
            """
            query get_bills($account_number: String!, $count: Int!) {
                account(accountNumber: $account_number) {
                    bills(first: $count, includeBillsWithoutPDF: false) {
                        edges {
                            node {
                                id
                                billType
                                temporaryUrl
                                issuedDate
                            }
                        }
                    }
                }
            }
            """,
            {"account_number": account_number, "count": count},
        )
        .get("data", {})
        .get("account", {})
        .get("bills", {})
        .get("edges", [])
    )


def download_bill(bill: dict, account: dict):
    tmpUrl = bill.get("temporaryUrl", None)
    if tmpUrl:
        fn = " ".join(
            [
                x
                for x in [
                    bill.get("issuedDate", "UnknownDate"),
                    bill.get("id", "UnknownBillID"),
                    bill["billType"].title()
                    if bill.get("billType", None)
                    else "UnknownBillType",
                    "-",
                    account["brand"].replace("_", " ").title()
                    if account.get("brand", None)
                    else "UnknownSupplier",
                    account["accountType"].title()
                    if account.get("accountType", None)
                    else "UnknownAccountType",
                    "-",
                    account["number"],
                    "-",
                    account.get("billingAddressLine1", "UnknownAddress"),
                    account["billingAddressPostcode"].replace(" ", "").upper()
                    if account.get("billingAddressPostcode", None)
                    else None,
                    account.get("billingCountryCode", None),
                ]
                if x
            ]
        )
        save_fn = f"{fn}.pdf"
        full_path = os.path.join(SAVE_LOCATION, save_fn)
        response = requests.get(tmpUrl)
        if response.ok and response.content:
            with open(full_path, mode="wb") as file:
                file.write(response.content)
            print("INFO: Downloaded:", full_path)


def run():
    for account in get_accounts():
        account_number = account.get("number", None)
        if account_number:
            print("INFO: Found account:", account_number)
            for bill_node in get_bills(account_number=account_number, count=BILL_COUNT):
                bill = bill_node.get("node", {})
                if BILL_COUNT == 1 and AUTORUN:
                    issuedDate = bill.get("issuedDate", "")
                    dateToday = datetime.now().strftime("%Y-%m-%d")
                    dateYest = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    if issuedDate != dateToday and issuedDate != dateYest:
                        print(
                            f"WARN: Skipping download of bill as issuedDate ({issuedDate}) is not today ({dateToday}) or yesterday ({dateYest})"
                        )
                        break
                download_bill(bill, account)


if AUTORUN:
    while True:
        timestr = datetime.now().strftime("%H:%M")
        if timestr == DOWNLOAD_TIME:
            try:
                run()
            except Exception as e:
                print("ERROR:", e)
            sleep(120)
        else:
            sleep(45)
else:
    run()
