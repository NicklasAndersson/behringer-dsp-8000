"""
DSP8000-modell: vad enheten kan och hur det mappas till MIDI.

REW kan inte ta emot en egen equaliser-modell (listan är inbyggd i appen,
API:t väljer bara {manufacturer, model}). Så vi modellerar enheten här och
mappar REW:s korrigeringskurva mot den själva.

Verifiera mot din egen enhets manual innan skarp körning - siffrorna kan
skilja mellan manualversioner, och MIDI CC->dB-skalan är okalibrerad.
"""

# 31 ISO-tersband, 20 Hz - 20 kHz (grafisk EQ per kanal)
ISO_BANDS = [
    20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500,
    630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000,
    10000, 12500, 16000, 20000,
]

# Manual (DSP8024 PRO, samma GEQ): grafisk EQ +16 till -16 dB i 0,5 dB-steg.
GRAPHIC_MAX_BOOST_DB = 16.0
GRAPHIC_MAX_CUT_DB = -16.0
GRAPHIC_STEP_DB = 0.5

# Auto-genererade korrigeringar: boosta lite (fyll aldrig upp djupa nullor -
# de är positionsberoende och äter headroom), men sänk toppar generöst.
SAFE_BOOST_DB = 3.0

PEQ_COUNT = 3  # 3 fullparametriska filter per kanal (delas med Feedback Destroyer)

# MIDI CC-mappning. Manualen (tab 7.2): CC 0-30 = vänster band (20 Hz..20 kHz),
# 31 = master vä, 32-62 = höger band, 63 = master hö. PLUS en inställbar
# "Controller Offset" (0-64) på MIDI-setup-sidan som adderas till alla numren.
# Sätt CC_OFFSET till samma värde som enhetens offset. Readme:s gamla "64-94"
# = offset 64. Testenheten stod på 0.
CC_OFFSET = 0
CC_GRAPHIC_LEFT = {f: CC_OFFSET + i for i, f in enumerate(ISO_BANDS)}
CC_MASTER_LEFT = CC_OFFSET + 31
CC_GRAPHIC_RIGHT = {f: CC_OFFSET + 32 + i for i, f in enumerate(ISO_BANDS)}
CC_MASTER_RIGHT = CC_OFFSET + 63
# Med Stereolink på räcker det att skicka vänsterkanalen.


def clamp_band_gain(db, max_boost=SAFE_BOOST_DB):
    """Runda till enhetens steg, klipp cut till enhetens gräns och boost
    till max_boost (default: den försiktiga SAFE_BOOST_DB)."""
    db = round(db / GRAPHIC_STEP_DB) * GRAPHIC_STEP_DB
    return max(GRAPHIC_MAX_CUT_DB, min(max_boost, db))


def db_to_cc(db):
    """
    dB -> CC-värde. Verifierat mot enheten 2026-09-02: CC 64 = 0 dB,
    CC 96 = +8 dB => CC = 64 + dB*4 (0,25 dB/steg). Klipps till 0..127
    (dvs -16 .. +15.75 dB; +16 dB nås inte, nära nog).
    """
    return max(0, min(127, round(64 + db * 4)))


if __name__ == "__main__":
    assert len(ISO_BANDS) == 31
    assert CC_GRAPHIC_LEFT[20] == 0 and CC_GRAPHIC_LEFT[1000] == 17
    assert CC_GRAPHIC_RIGHT[1000] == 49 and CC_MASTER_LEFT == 31
    assert clamp_band_gain(2.1) == 2.0
    assert clamp_band_gain(9.0) == 3.0        # boost kapas till SAFE_BOOST_DB
    assert clamp_band_gain(9.0, max_boost=12) == 9.0
    assert clamp_band_gain(-99) == -16.0
    assert db_to_cc(0) == 64 and db_to_cc(8) == 96  # 8 dB verifierat mot enheten
    assert db_to_cc(-16) == 0 and db_to_cc(16) == 127
    print("dsp8000: självtest ok")
