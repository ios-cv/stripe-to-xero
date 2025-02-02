import os

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import stripe
import xero_python.accounting
from xero_python.api_client import ApiClient
from xero_python.api_client.configuration import Configuration
from xero_python.api_client.oauth2 import OAuth2Token
from xero_python.identity import IdentityApi
from xero_python.accounting import AccountingApi, Contact, Contacts, Invoice, LineItem, Invoices, LineItemTracking, \
    Payment, Account
from xero_python.utils import getvalue

XERO_CLIENT_ID = os.getenv("XERO_CLIENT_ID")
XERO_CLIENT_SECRET = os.getenv("XERO_CLIENT_SECRET")

XERO_GENERIC_CUSTOMER_CONTACT_ID = os.getenv("XERO_GENERIC_CUSTOMER_CONTACT_ID")
XERO_TRACKING_CATEGORY_ONE_ID = os.getenv("XERO_TRACKING_CATEGORY_ONE_ID")
XERO_TRACKING_CATEGORY_ONE_OPTION_ID = os.getenv("XERO_TRACKING_CATEGORY_ONE_OPTION_ID")
XERO_TRACKING_CATEGORY_TWO_ID = os.getenv("XERO_TRACKING_CATEGORY_TWO_ID")
XERO_TRACKING_CATEGORY_TWO_OPTION_ID = os.getenv("XERO_TRACKING_CATEGORY_TWO_OPTION_ID")
XERO_ACCOUNT_STRIPE_SALES = os.getenv("XERO_ACCOUNT_STRIPE_SALES")
XERO_ACCOUNT_STRIPE_SALES_LONG_TERM = os.getenv("XERO_ACCOUNT_STRIPE_SALES_LONG_TERM")
XERO_ACCOUNT_STRIPE_BANK = os.getenv("XERO_ACCOUNT_STRIPE_BANK")
XERO_CONTACT_IDS_LONG_TERM = os.getenv("XERO_CONTACT_IDS_LONG_TERM").split(",")

api_client = ApiClient(
    Configuration(
        debug=False,
        oauth2_token=OAuth2Token(
            client_id=XERO_CLIENT_ID, client_secret=XERO_CLIENT_SECRET,
        ),
    ),
    pool_threads=1,
)

TOKEN = None

TZ = ZoneInfo("Europe/London")


@api_client.oauth2_token_getter
def obtain_xero_oauth2_token():
    return TOKEN


@api_client.oauth2_token_saver
def store_xero_oauth2_token(token):
    global TOKEN
    TOKEN = token


class XeroClient:
    def init(self):
        try:
            xero_token = api_client.get_client_credentials_token()
        except Exception as e:
            print(e)
            raise

        if xero_token is None or xero_token.get("access_token") is None:
            print("Access denied: response=%s" % xero_token)
            return

        print("******* Doing identity ID Bit *********")
        identity_api = IdentityApi(api_client)
        for connection in identity_api.get_connections():
            if connection.tenant_type == "ORGANISATION":
                self.tenant_id = connection.tenant_id
                print(f"Tenant ID: {self.tenant_id}")

        print("Init done.")

        self.accounting_api = AccountingApi(api_client)

    def get_invoice_by_number(self, invoice_number):
        where = f'InvoiceNumber=="{invoice_number}"'

        r = self.accounting_api.get_invoices(self.tenant_id, where=where)

        # print(r)
        print(r)

        return getvalue(r, "invoices.0")

    def migrate_invoice(self, invoice):
        accounting_api = AccountingApi(api_client)

        number = invoice['number']
        due_date = datetime.fromtimestamp(invoice['due_date'], TZ) if invoice['due_date'] is not None else None
        date = datetime.fromtimestamp(invoice['status_transitions']['finalized_at'], TZ)
        collection_method = invoice["collection_method"]

        print(f"Inv Number: {number}")
        print(f"Date: {date}, Due Date: {due_date}")

        # Check if invoice already exists in Xero.
        xi = self.get_invoice_by_number(number)

        if not xi:
            print("... creating Xero invoice.")
            # Need to create an invoice.
            if collection_method == "charge_automatically":
                x_contact = Contact(
                    contact_id=XERO_GENERIC_CUSTOMER_CONTACT_ID,
                )

            elif collection_method == "send_invoice":
                x_contact = self.get_or_create_contact(invoice)
            
            account = XERO_ACCOUNT_STRIPE_SALES
            if x_contact.contact_number in XERO_CONTACT_IDS_LONG_TERM:
                account = XERO_ACCOUNT_STRIPE_SALES_LONG_TERM

            x_line_items = self.migrate_line_items(invoice, account)

            x_invoice = Invoice(
                invoice_number=number,
                line_items=x_line_items,
                contact=x_contact,
                date=date,
                due_date=due_date or date + timedelta(days=7),
                type="ACCREC",
                status="AUTHORISED",
                sent_to_contact=True,
            )

            x_invoices = Invoices(invoices=[x_invoice])
            created_invoices = accounting_api.create_invoices(self.tenant_id, invoices=x_invoices)
            # print(created_invoices)
            xi = getvalue(created_invoices, "invoices.0")

        # print(xi)

        if (xi.payments is None or len(xi.payments) == 0) and collection_method == "charge_automatically":
            print("... adding payment to Xero")
            if invoice["paid"] and not invoice["paid_out_of_band"]:
                x_payment = Payment(
                    invoice=xi,
                    date=datetime.fromtimestamp(invoice['status_transitions']['paid_at'], TZ),
                    amount=xi.total,
                    account=Account(code=XERO_ACCOUNT_STRIPE_BANK),
                    reference=invoice["charge"],
                )
                r = self.accounting_api.create_payment(self.tenant_id, payment=x_payment)
                # print(r)

    def migrate_line_items(self, invoice, account):
        x_lines = []

        x_tc = []
        if XERO_TRACKING_CATEGORY_ONE_ID and len(XERO_TRACKING_CATEGORY_ONE_ID) > 0:
            x_tc.append(LineItemTracking(
                tracking_category_id=XERO_TRACKING_CATEGORY_ONE_ID,
                tracking_option_id=XERO_TRACKING_CATEGORY_ONE_OPTION_ID,
            ))

        if XERO_TRACKING_CATEGORY_TWO_ID and len(XERO_TRACKING_CATEGORY_TWO_ID) > 0:
            x_tc.append(LineItemTracking(
                tracking_category_id=XERO_TRACKING_CATEGORY_TWO_ID,
                tracking_option_id=XERO_TRACKING_CATEGORY_TWO_OPTION_ID,
            ))

        line = None
        while True:
            lines = invoice.lines.list(starting_after=line)

            for line in lines['data']:
                x_l = LineItem(
                    account_code=account,
                    description=f"{line['description']} (Quantity: {line['quantity']})",
                    #quantity=line["quantity"], # Disable quantity to ensure we don't have any rounding issues with VAT.
                    line_amount=line["amount_excluding_tax"] / 100,
                    tax_amount=(line["amount"] - line["amount_excluding_tax"]) / 100,
                    tracking=x_tc,
                )
                x_lines.append(x_l)

            if not lines['has_more']:
                break

        return x_lines

    def get_or_create_contact(self, invoice):
        contacts = self.accounting_api.get_contacts(self.tenant_id, where=f'ContactNumber=="{invoice["customer"]}"')

        if len(contacts.contacts) > 0:
            return Contact(contact_id=getvalue(contacts, "contacts.0.contact_id", ""))

        contacts = self.accounting_api.create_contacts(self.tenant_id, Contacts([
            Contact(name=f"{invoice['customer_name']}", contact_number=invoice["customer"])
        ]))

        return Contact(contact_id=getvalue(contacts, "contacts.0.contact_id", ""))

    def dump_tracking_categories(self):
        accounting_api = AccountingApi(api_client)
        tc = accounting_api.get_tracking_categories(self.tenant_id)
        print(tc)

    def dump_chart_of_accounts(self):
        acc = self.accounting_api.get_accounts(self.tenant_id)
        print(acc)
