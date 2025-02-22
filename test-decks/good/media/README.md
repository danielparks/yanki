# Media for test-decks/good

Files not listed are files that I created from scratch.

### [stopwatch.mp4](stopwatch.mp4)

I forked Yusuf Sezer’s [analog clock demo][] and turned it into a [stopwatch][].
I took screenshots, and used them to generate a video with a a repeating tone:

    ffmpeg -hide_banner -y -framerate 60 -i shot_%02d.png \
      -filter_complex "aevalsrc='sin(5*2*PI*t)*sin(220*2*PI*t)':d=1[a]" \
      -map '0:v' -map '[a]' -c:v libx264 -pix_fmt yuv420p -preset slow out.mp4

[analog clock demo]: https://www.yusufsezer.com/analog-clock/
[stopwatch]: https://github.com/danielparks/analog-clock
