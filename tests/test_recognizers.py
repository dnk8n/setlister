from setlister.identify import CachedRecognizer, RecognizerError
from setlister.models import Source, TrackRef


class Fake:
    name = Source.SHAZAM

    def __init__(self, answers):
        self.answers, self.calls = list(answers), 0

    def available(self):
        return True, ""

    def recognize(self, wav):
        self.calls += 1
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def wav(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_answers_are_cached_so_reruns_do_not_ask_again(tmp_path):
    hit = [(TrackRef(artist="A", title="B"), 0.8)]
    first = CachedRecognizer(Fake([hit, []]), tmp_path)
    assert first.recognize(wav(tmp_path, "1.wav", b"one")) == hit
    assert first.recognize(wav(tmp_path, "2.wav", b"two")) == []
    again = CachedRecognizer(Fake([]), tmp_path)  # would fail if it asked
    assert again.recognize(wav(tmp_path, "3.wav", b"one")) == hit
    assert again.recognize(wav(tmp_path, "4.wav", b"two")) == []
    assert (again.asked, again.cached) == (0, 2)


def test_gives_up_after_repeated_failures_and_does_not_cache_them(tmp_path):
    fake = Fake([RecognizerError("429")] * 3)
    r = CachedRecognizer(fake, tmp_path, give_up_after=3)
    for i in range(5):
        assert r.recognize(wav(tmp_path, f"{i}.wav", bytes([i]))) == []
    assert r.gave_up and fake.calls == 3
    assert "gave up" in r.summary()
    assert not list((tmp_path / "recognitions").rglob("*.json"))
