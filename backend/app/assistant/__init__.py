"""ToyVault AI Assist — an OpenAI tool-calling assistant embedded in the backend.

It answers business questions by calling the app's OWN read-only analytics
functions in-process (the same code that serves the dashboard pages), so every
figure it reports matches the pages exactly. The model orchestrates and explains;
it never computes a number itself.
"""
