"""Lasso Issues."""
import importlib.resources

__version__ = importlib.resources.files(__name__).joinpath("VERSION.txt").read_text().strip()
