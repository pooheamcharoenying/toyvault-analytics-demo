"""LINE Messaging API integration — Team Assist over LINE.

LINE is just another front door to the same assistant: a webhook receives a staff
member's message, we map their LINE id to their ToyVault account, run the SAME
agent, and push the answer back. Signature-verified; the webhook is public (LINE
authenticates by signature, not Basic auth).
"""
