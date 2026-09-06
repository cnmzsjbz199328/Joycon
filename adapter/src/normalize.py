"""DecodedPacket -> InputFrame (the §8.1 wire contract).

Calibration (if any) is applied *before* this by the caller, so here we just
reshape and attach the adapter timestamp.
"""

from __future__ import annotations

from shared.protocol.frame import InputFrame

from .decoder.packet import DecodedPacket


def to_input_frame(pkt: DecodedPacket, timestamp: float) -> InputFrame:
    return InputFrame(
        timestamp=timestamp,
        seq=pkt.seq,
        controller=pkt.side,
        buttons=pkt.buttons,
        stick=pkt.stick,
        accel_g=(pkt.accel_g.x, pkt.accel_g.y, pkt.accel_g.z),
        gyro_dps=(pkt.gyro_dps.x, pkt.gyro_dps.y, pkt.gyro_dps.z),
        battery_v=pkt.battery_v,
        battery_ma=pkt.battery_ma,
        temperature_c=pkt.temperature_c,
    )
