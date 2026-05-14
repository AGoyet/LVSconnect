#!/usr/bin/env python3
import functools

def cli():
    from lvsconnect.pronotepy.ent import ent, complex_ent
    ent_names = set()
    for module in [ent, complex_ent]:
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if callable(obj):
                # Skip classes (like exceptions, partial itself, BeautifulSoup)
                if isinstance(obj, type):
                    continue
                if isinstance(obj, functools.partial):
                    pass # It's a partial (like the ones in ent.py)
                # If it's a function, check if it was defined in the module
                elif hasattr(obj, '__module__'):
                    if obj.__module__ != module.__name__:
                        continue
                else:
                    continue # Some other callable without __module__
                ent_names.add(name)
    for name in sorted(ent_names):
        print(name)

if __name__ == "__main__":
    cli()
