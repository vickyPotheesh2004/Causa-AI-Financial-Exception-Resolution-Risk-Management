# Razorpay public-schema sample

This JSON contains fictional normalized records shaped from Razorpay's public payment-entity documentation. It is not exported from Razorpay, does not contain real transactions, and does not contain card or customer data.

Cause AI uses whole INR amounts in this normalized schema. Razorpay's API uses currency subunits; the connector converts that representation before records enter Cause AI.

Use the Detection lab's **Load Razorpay public-schema sample** button to test the settlement-mismatch workflow. Its records remain unverified and must never be represented as payment evidence.
