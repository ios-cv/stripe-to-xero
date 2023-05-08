import os
import stripe

from datetime import datetime
from zoneinfo import ZoneInfo

from xero import XeroClient

REQUIRED_CONFIG = [
    "STRIPE_SECRET_KEY",
]

TZ = ZoneInfo("Europe/London")

START_DATE = int(datetime.strptime(os.getenv("START_DATE") + " 00:00:00", "%Y-%m-%d %H:%M:%S").timestamp())
END_DATE = int(datetime.strptime(os.getenv("END_DATE") + " 23:59:59", "%Y-%m-%d %H:%M:%S").timestamp())


def check_config():
    for k in REQUIRED_CONFIG:
        if not os.getenv(k):
            raise Exception(f"Environment variable ${k} is required.")


def stripe_init():
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


def xero_init():
    c = XeroClient()
    c.init()
    return c


def migrate(xc):
    invoice = None

    print(f"Start Date: {START_DATE} End Date: {END_DATE}")

    while True:
        invoices = stripe.Invoice.list(limit=100, starting_after=invoice,
                                       created={"gte": START_DATE - 2678400, "lt": END_DATE})
        for invoice in invoices["data"]:
            print(
                f"[{invoice['status']}] New invoice retrieved for {invoice['customer_name']} with total amount £{invoice['total'] / 100}."
            )

            ts = datetime.fromtimestamp(invoice["created"], TZ)
            print(f"    Created At: {ts.isoformat()}.")

            if invoice["collection_method"] == "charge_automatically":
                print(f"    Charged automatically to card.")
            else:
                print(f"    Collection Method: {invoice['collection_method']}.")

            # Process Invoice
            if invoice['status'] == 'draft':
                continue
            else:
                if not (START_DATE <= invoice["status_transitions"]["finalized_at"] <= END_DATE):
                    print(f"  !! Skipping invoice that was not finalised within the desired time window.")
                    continue
                xc.migrate_invoice(invoice)

        # break
        if not invoices["has_more"]:
            break


if __name__ == "__main__":
    check_config()
    stripe_init()
    xc = xero_init()
    # xc.get_invoice_by_number("GOEV-0001")
    # xc.dump_tracking_categories()
    # xc.dump_chart_of_accounts()

    migrate(xc)
