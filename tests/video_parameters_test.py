import pytest

from yanki.video import Video, VideoOptions


def get_video(tmp_path):
    cache_path = tmp_path / "cache"
    cache_path.mkdir(parents=True, exist_ok=True)

    return Video(
        "file://./test-decks/good/media/stopwatch.mp4",
        options=VideoOptions(cache_path=cache_path),
    )


def test_time_parse(tmp_path):  # noqa: PLR0915 (too many statements)
    video = get_video(tmp_path)

    assert video.get_fps() == 60

    assert video.time_to_seconds(0, on_none="a") == 0
    assert video.time_to_seconds("", on_none="a") == "a"
    assert video.time_to_seconds(None, on_none="a") == "a"

    assert round(video.time_to_seconds("123.4"), 9) == 123.4
    assert round(video.time_to_seconds("123.4s"), 9) == 123.4
    assert round(video.time_to_seconds("123.4S"), 9) == 123.4
    assert round(video.time_to_seconds("123.4ms"), 9) == 0.1234
    assert round(video.time_to_seconds("123.4MS"), 9) == 0.1234
    assert round(video.time_to_seconds("123.4Ms"), 9) == 0.1234
    assert round(video.time_to_seconds("123.4mS"), 9) == 0.1234
    assert round(video.time_to_seconds("123.4us"), 9) == 0.0001234
    assert round(video.time_to_seconds("123.4US"), 9) == 0.0001234
    assert round(video.time_to_seconds("123.4Us"), 9) == 0.0001234
    assert round(video.time_to_seconds("123.4uS"), 9) == 0.0001234
    assert round(video.time_to_seconds("-2S"), 9) == -2

    assert round(video.time_to_seconds("2 s"), 9) == 2

    with pytest.raises(ValueError) as error_info:
        video.time_to_seconds("2ks")
    assert error_info.match("could not convert string to float")

    assert round(video.time_to_seconds("0:45.6"), 9) == 45.6
    assert round(video.time_to_seconds("1:45.6"), 9) == 60 + 45.6
    assert round(video.time_to_seconds("1:1:45.6"), 9) == 3600 + 60 + 45.6
    assert (
        round(video.time_to_seconds("1:23:45.6"), 9)
        == (1 * 60 + 23) * 60 + 45.6
    )
    assert (
        round(video.time_to_seconds("02:03:05.6"), 9) == (2 * 60 + 3) * 60 + 5.6
    )

    assert round(video.time_to_seconds("-0:45.6"), 9) == -45.6
    assert round(video.time_to_seconds("-1:45.6"), 9) == -(60 + 45.6)
    assert round(video.time_to_seconds("-1:1:45.6"), 9) == -(3600 + 60 + 45.6)
    assert round(video.time_to_seconds("-1:23:45.6"), 9) == -(
        (1 * 60 + 23) * 60 + 45.6
    )
    assert round(video.time_to_seconds("-02:03:05.6"), 9) == -(
        (2 * 60 + 3) * 60 + 5.6
    )

    with pytest.raises(ValueError) as error_info:
        video.time_to_seconds(":2")
    assert error_info.match("could not convert string to float")

    with pytest.raises(ValueError) as error_info:
        video.time_to_seconds("2:")
    assert error_info.match("could not convert string to float")

    with pytest.raises(ValueError) as error_info:
        video.time_to_seconds("af:2")
    assert error_info.match("could not convert string to float")

    # FIXME? Should probably be error
    assert (
        round(video.time_to_seconds("2.1:3:5.6"), 9)
        == (2.1 * 60 + 3) * 60 + 5.6
    )

    # Frames
    assert round(video.time_to_seconds("0f"), 9) == 0
    assert round(video.time_to_seconds("1F"), 9) == round(1 / 60, 9)
    assert round(video.time_to_seconds("2F"), 9) == round(2 / 60, 9)
    assert round(video.time_to_seconds("-2F"), 9) == round(-2 / 60, 9)

    with pytest.raises(ValueError) as error_info:
        video.time_to_seconds("2fF")
    assert error_info.match("invalid literal")

    with pytest.raises(ValueError) as error_info:
        video.time_to_seconds("2F0")
    assert error_info.match("could not convert string to float")
