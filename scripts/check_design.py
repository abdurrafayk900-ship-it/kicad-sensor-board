#!/usr/bin/env python3
"""Sanity-check the board netlist against the BOM before layout.

Checks:
  * every net connects at least two pins (no dangling nets)
  * no component pin is assigned to two nets
  * every netlist reference is in the BOM and vice versa
  * BOM quantities match the number of references
  * required power nets exist
Also prints a per-net summary and the BOM cost per board.

Usage: python scripts/check_design.py [--boards N]
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

HW = Path(__file__).resolve().parent.parent / "hardware"
REQUIRED_NETS = {"GND", "+3V3", "+5V"}


def load_netlist(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_bom(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check(netlist: list[dict], bom: list[dict]) -> list[str]:
    errors: list[str] = []

    nets: dict[str, list[str]] = defaultdict(list)
    pin_to_net: dict[str, str] = {}
    for row in netlist:
        pin = f"{row['ref']}.{row['pin']}"
        if pin in pin_to_net and pin_to_net[pin] != row["net"]:
            errors.append(f"{pin} is on two nets: {pin_to_net[pin]} and {row['net']}")
        pin_to_net[pin] = row["net"]
        nets[row["net"]].append(pin)

    for net, pins in sorted(nets.items()):
        if len(pins) < 2:
            errors.append(f"Net {net} only connects {pins[0]} (dangling)")

    missing_power = REQUIRED_NETS - nets.keys()
    if missing_power:
        errors.append(f"Missing power nets: {', '.join(sorted(missing_power))}")

    net_refs = {row["ref"] for row in netlist}
    bom_refs: set[str] = set()
    for line in bom:
        refs = line["refs"].split()
        if len(refs) != int(line["qty"]):
            errors.append(f"BOM line {line['refs']!r}: qty {line['qty']} but {len(refs)} refs")
        bom_refs.update(refs)

    for ref in sorted(net_refs - bom_refs):
        errors.append(f"{ref} is in the netlist but not the BOM")
    for ref in sorted(bom_refs - net_refs):
        errors.append(f"{ref} is in the BOM but not connected in the netlist")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", type=int, default=5, help="Board quantity for cost estimate")
    args = ap.parse_args()

    netlist = load_netlist(HW / "netlist.csv")
    bom = load_bom(HW / "bom.csv")

    nets: dict[str, list[str]] = defaultdict(list)
    for row in netlist:
        nets[row["net"]].append(f"{row['ref']}.{row['pin']}")

    print(f"{'NET':14} {'PINS':>4}  CONNECTIONS")
    for net in sorted(nets, key=lambda n: (-len(nets[n]), n)):
        pins = nets[net]
        shown = " ".join(pins[:8]) + (" ..." if len(pins) > 8 else "")
        print(f"{net:14} {len(pins):>4}  {shown}")

    per_board = sum(float(b["unit_cost_usd"]) * int(b["qty"]) for b in bom)
    parts = sum(int(b["qty"]) for b in bom)
    print(f"\n{len(nets)} nets, {len({r['ref'] for r in netlist})} components, {parts} placed parts")
    print(f"BOM cost: ${per_board:.2f}/board, ${per_board * args.boards:.2f} for {args.boards} boards")

    errors = check(netlist, bom)
    if errors:
        print(f"\n{len(errors)} problem(s) found:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
