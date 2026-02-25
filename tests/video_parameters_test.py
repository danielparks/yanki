import logging
from math import isclose

import pytest

from yanki.video import Video, VideoOptions

LOGGER = logging.getLogger(__name__)


def get_video():
    return Video(
        "file://./test-decks/good/media/stopwatch.mp4",
        options=VideoOptions(),
    )


def test_time_parse():  # noqa: PLR0915 (too many statements)
    video = get_video()

    assert video.get_fps() == 60

    assert video.time_to_seconds(0, on_none="a") == 0
    assert video.time_to_seconds("", on_none="a") == "a"
    assert video.time_to_seconds(None, on_none="a") == "a"

    assert isclose(video.time_to_seconds("123.4"), 123.4)
    assert isclose(video.time_to_seconds("123.4s"), 123.4)
    assert isclose(video.time_to_seconds("123.4S"), 123.4)
    assert isclose(video.time_to_seconds("123.4ms"), 0.1234)
    assert isclose(video.time_to_seconds("123.4MS"), 0.1234)
    assert isclose(video.time_to_seconds("123.4Ms"), 0.1234)
    assert isclose(video.time_to_seconds("123.4mS"), 0.1234)
    assert isclose(video.time_to_seconds("123.4us"), 0.0001234)
    assert isclose(video.time_to_seconds("123.4US"), 0.0001234)
    assert isclose(video.time_to_seconds("123.4Us"), 0.0001234)
    assert isclose(video.time_to_seconds("123.4uS"), 0.0001234)
    assert isclose(video.time_to_seconds("-2S"), -2)

    assert isclose(video.time_to_seconds("2 s"), 2)

    with pytest.raises(ValueError) as error_info:
        video.time_to_seconds("2ks")
    LOGGER.info("Caught exception", exc_info=error_info.value)
    assert error_info.match("could not convert string to float")

    assert isclose(video.time_to_seconds("0:45.6"), 45.6)
    assert isclose(video.time_to_seconds("1:45.6"), 60 + 45.6)
    assert isclose(video.time_to_seconds("1:1:45.6"), 3600 + 60 + 45.6)
    assert isclose(
        video.time_to_seconds("1:23:45.6"), (1 * 60 + 23) * 60 + 45.6
    )
    assert isclose(video.time_to_seconds("02:03:05.6"), (2 * 60 + 3) * 60 + 5.6)

    assert isclose(video.time_to_seconds("-0:45.6"), -45.6)
    assert isclose(video.time_to_seconds("-1:45.6"), -(60 + 45.6))
    assert isclose(video.time_to_seconds("-1:1:45.6"), -(3600 + 60 + 45.6))
    assert isclose(
        video.time_to_seconds("-1:23:45.6"),
        -((1 * 60 + 23) * 60 + 45.6),
    )
    assert isclose(
        video.time_to_seconds("-02:03:05.6"),
        -((2 * 60 + 3) * 60 + 5.6),
    )

    with pytest.raises(ValueError) as error_info:
        video.time_to_seconds(":2")
    LOGGER.info("Caught exception", exc_info=error_info.value)
    assert error_info.match("could not convert string to float")

    with pytest.raises(ValueError) as error_info:
        video.time_to_seconds("2:")
    LOGGER.info("Caught exception", exc_info=error_info.value)
    assert error_info.match("could not convert string to float")

    with pytest.raises(ValueError) as error_info:
        video.time_to_seconds("af:2")
    LOGGER.info("Caught exception", exc_info=error_info.value)
    assert error_info.match("could not convert string to float")

    # FIXME? Should probably be error
    assert isclose(
        video.time_to_seconds("2.1:3:5.6"), (2.1 * 60 + 3) * 60 + 5.6
    )

    # Frames
    assert isclose(video.time_to_seconds("0f"), 0)
    assert isclose(video.time_to_seconds("1F"), 1 / 60)
    assert isclose(video.time_to_seconds("2F"), 2 / 60)
    assert isclose(video.time_to_seconds("-2F"), -2 / 60)

    with pytest.raises(ValueError) as error_info:
        video.time_to_seconds("2fF")
    LOGGER.info("Caught exception", exc_info=error_info.value)
    assert error_info.match("invalid literal")

    with pytest.raises(ValueError) as error_info:
        video.time_to_seconds("2F0")
    LOGGER.info("Caught exception", exc_info=error_info.value)
    assert error_info.match("could not convert string to float")
