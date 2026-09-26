"""Compatibility entry: use explicit-font v0.5 overlay input; old layouts must be requalified."""
import argparse
from exact_overlay import compose
if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('spec'); p.add_argument('out'); p.add_argument('--font',required=True)
    a=p.parse_args(); compose(a.spec,a.out,a.font)
