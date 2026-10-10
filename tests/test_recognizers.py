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


def test_backs_off_then_gives_up_and_does_not_cache_failures(tmp_path):
    fake = Fake([RecognizerError("429")] * 3)
    waits = []
    r = CachedRecognizer(
        fake, tmp_path, backoff=(0.0, 0.0), on_wait=lambda s, why: waits.append(why)
    )
    for i in range(5):
        assert r.recognize(wav(tmp_path, f"{i}.wav", bytes([i]))) == []
    assert r.gave_up and fake.calls == 3 and waits == ["429", "429"]
    assert "stopped" in r.summary()
    assert not list((tmp_path / "recognitions").rglob("*.json"))


def test_a_retry_that_succeeds_carries_on(tmp_path):
    hit = [(TrackRef(artist="A", title="B"), 0.8)]
    r = CachedRecognizer(Fake([RecognizerError("429"), hit]), tmp_path, backoff=(0.0,))
    assert r.recognize(wav(tmp_path, "1.wav", b"x")) == hit and not r.gave_up


def test_rejected_acoustid_key_stops_at_once_with_a_clear_reason(tmp_path):
    from setlister.identify.acoustid_rec import check_response

    def rejected(wav):
        check_response({"status": "error", "error": {"code": 4, "message": "invalid API key"}})

    fake = Fake([])
    fake.recognize = rejected
    r = CachedRecognizer(fake, tmp_path)
    assert r.recognize(wav(tmp_path, "1.wav", b"x")) == []
    assert r.gave_up and "application key" in r.reason


def test_other_acoustid_errors_are_retryable():
    import pytest

    from setlister.identify import PermanentRecognizerError
    from setlister.identify.acoustid_rec import check_response

    with pytest.raises(RecognizerError) as e:
        check_response({"status": "error", "error": {"code": 14, "message": "rate limit"}})
    assert not isinstance(e.value, PermanentRecognizerError)
    check_response({"status": "ok", "results": []})
