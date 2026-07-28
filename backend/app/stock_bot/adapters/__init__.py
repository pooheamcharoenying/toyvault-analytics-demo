"""Adapters — the only place in stock_bot that touches pandas / GLOBAL_DF.

Each module exposes one or two public functions that return either plain
DataFrames or plain domain objects. The rest of the package is pandas-free.
"""
