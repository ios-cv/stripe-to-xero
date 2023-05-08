xero-to-stripe
==============

This is a utility script that idempotently synchronises invoices raised in Stripe Billing over
to Xero. For invoices charged to cards automatically, it uses a generic customer in Xero to
avoid cluttering up the Xero Contacts list. For invoices *not* charge automatically, it creates
individual customers in Xero.

For invoices that have been charged automatically, it also creates payments against a Xero Bank
Account. This allows for easy reconciliation of a Stripe Account connected with Xero Bank Feeds.

*Warning*: This script is very hacky/work-in-progress. It does just enough for what we need, but
not in a particularly clean or efficient way. You probably want to use it as a starting point
for customisation rather than treating it as a finished product...

Requirements
------------

1. Python
2. Patience
3. A Xero Custom Connection subscription (paid add on feature costing £5 per month).

Usage
-----

Set up a Xero Custom Connection app in the Xero developer center. Attach it to the Xero Account
you want to sync data into.

Set up your shell environment with the required environment variables:

```shell
export STRIPE_SECRET_KEY=
export XERO_CLIENT_ID=
export XERO_CLIENT_SECRET=

export XERO_GENERIC_CUSTOMER_CONTACT_ID=
export XERO_ACCOUNT_STRIPE_SALES=
export XERO_ACCOUNT_STRIPE_BANK=
export XERO_TRACKING_CATEGORY_ONE_ID=
export XERO_TRACKING_CATEGORY_ONE_OPTION_ID=
export XERO_TRACKING_CATEGORY_TWO_ID=
export XERO_TRACKING_CATEGORY_TWO_OPTION_ID=

export START_DATE=
export END_DATE=
```

Install the dependencies:

```shell
$ poetry install
```

Run the script
```shell
poetry run src/main.py
```

**Warning**: Before running a random script you found on the Internet against your Xero account,
you should definitely make sure you understand how it works in a Demo account first!

