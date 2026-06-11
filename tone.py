"""Tone — buzzer / tone output.

NOTE: the firmware currently STUBS this (no buzzer wired yet). Commands are
accepted and logged but produce no sound. When a buzzer is wired to BUZZER_PIN,
enable the tone() call in the firmware's toneStub().

    tone = Tone(link)
    tone.play(1000, 200)   # 1000 Hz for 200 ms
"""


class Tone:
    def __init__(self, link):
        self._link = link

    def play(self, freq=1000, ms=200):
        self._link.send(f"TONE {int(freq)} {int(ms)}")
