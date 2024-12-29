# Media for test-decks/good

Files not listed are files that I created from scratch.

### [stopwatch.mp4](stopwatch.mp4)

This is a screen recording I made of Yusuf Sezer’s [analog clock demo][] after
modifying it (in the web inspector) to have a second and sub-second hand like a
stopwatch. [The original code][analog clock code] is available under an [MIT
license][analog clock license].

I added a repeating tone to it with a command like the following:

    ffmpeg -y -i silent-stopwatch.mp4 \
      -filter_complex "aevalsrc='sin(5*2*PI*t)*sin(220*2*PI*t)':d=5.0167[a]" \
      -map '0:v' \
      -map '[a]' \
      test-decks/good/media/stopwatch.mp4

[analog clock demo]: https://www.yusufsezer.com/analog-clock/
[analog clock code]: https://github.com/yusufsefasezer/analog-clock
[analog clock license]: https://github.com/yusufsefasezer/analog-clock/blob/daac8d8ea85ca7d91c55671ad411414d400c0994/LICENSE
