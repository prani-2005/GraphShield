"""Generate 150 deterministic evaluation cases from original Olist order IDs.
Gold labels use an invented demo policy; they are not real support outcomes.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from graphshield.refund_desk import save_cases
if __name__=='__main__':
    print(save_cases())
