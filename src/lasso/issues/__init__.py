"""Lasso Issues."""
import importlib

__version__ = importlib.resources.files(__name__).joinpath("VERSION.txt").read_text().strip()
