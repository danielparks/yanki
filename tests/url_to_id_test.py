from yanki.video import url_to_id

# From the following gist, modified to all use the same ID.
# https://gist.github.com/rodrigoborgesdeoliveira/987683cfbfcc8d800192da1e73adc486
YOUTUBE_ID = "lalOy8Mbfdc"
YOUTUBE_URLS = """
http://www.youtube.com/watch?v=lalOy8Mbfdc
http://youtube.com/watch?v=lalOy8Mbfdc
http://m.youtube.com/watch?v=lalOy8Mbfdc
https://www.youtube.com/watch?v=lalOy8Mbfdc
https://youtube.com/watch?v=lalOy8Mbfdc
https://m.youtube.com/watch?v=lalOy8Mbfdc

http://www.youtube.com/watch?v=lalOy8Mbfdc&feature=em-uploademail
http://youtube.com/watch?v=lalOy8Mbfdc&feature=em-uploademail
http://m.youtube.com/watch?v=lalOy8Mbfdc&feature=em-uploademail
https://www.youtube.com/watch?v=lalOy8Mbfdc&feature=em-uploademail
https://youtube.com/watch?v=lalOy8Mbfdc&feature=em-uploademail
https://m.youtube.com/watch?v=lalOy8Mbfdc&feature=em-uploademail

http://www.youtube.com/watch?v=lalOy8Mbfdc&feature=feedrec_grec_index
http://youtube.com/watch?v=lalOy8Mbfdc&feature=feedrec_grec_index
http://m.youtube.com/watch?v=lalOy8Mbfdc&feature=feedrec_grec_index
https://www.youtube.com/watch?v=lalOy8Mbfdc&feature=feedrec_grec_index
https://youtube.com/watch?v=lalOy8Mbfdc&feature=feedrec_grec_index
https://m.youtube.com/watch?v=lalOy8Mbfdc&feature=feedrec_grec_index

http://www.youtube.com/watch?v=lalOy8Mbfdc#t=0m10s
http://youtube.com/watch?v=lalOy8Mbfdc#t=0m10s
http://m.youtube.com/watch?v=lalOy8Mbfdc#t=0m10s
https://www.youtube.com/watch?v=lalOy8Mbfdc#t=0m10s
https://youtube.com/watch?v=lalOy8Mbfdc#t=0m10s
https://m.youtube.com/watch?v=lalOy8Mbfdc#t=0m10s

http://www.youtube.com/watch?v=lalOy8Mbfdc&feature=channel
http://youtube.com/watch?v=lalOy8Mbfdc&feature=channel
http://m.youtube.com/watch?v=lalOy8Mbfdc&feature=channel
https://www.youtube.com/watch?v=lalOy8Mbfdc&feature=channel
https://youtube.com/watch?v=lalOy8Mbfdc&feature=channel
https://m.youtube.com/watch?v=lalOy8Mbfdc&feature=channel

http://www.youtube.com/watch?v=lalOy8Mbfdc&playnext_from=TL&videos=osPknwzXEas&feature=sub
http://youtube.com/watch?v=lalOy8Mbfdc&playnext_from=TL&videos=osPknwzXEas&feature=sub
http://m.youtube.com/watch?v=lalOy8Mbfdc&playnext_from=TL&videos=osPknwzXEas&feature=sub
https://www.youtube.com/watch?v=lalOy8Mbfdc&playnext_from=TL&videos=osPknwzXEas&feature=sub
https://youtube.com/watch?v=lalOy8Mbfdc&playnext_from=TL&videos=osPknwzXEas&feature=sub
https://m.youtube.com/watch?v=lalOy8Mbfdc&playnext_from=TL&videos=osPknwzXEas&feature=sub

http://www.youtube.com/watch?v=lalOy8Mbfdc&feature=youtu.be
http://youtube.com/watch?v=lalOy8Mbfdc&feature=youtu.be
http://m.youtube.com/watch?v=lalOy8Mbfdc&feature=youtu.be
https://www.youtube.com/watch?v=lalOy8Mbfdc&feature=youtu.be
https://youtube.com/watch?v=lalOy8Mbfdc&feature=youtu.be
https://m.youtube.com/watch?v=lalOy8Mbfdc&feature=youtu.be

http://www.youtube.com/watch?v=lalOy8Mbfdc&feature=youtube_gdata_player
http://youtube.com/watch?v=lalOy8Mbfdc&feature=youtube_gdata_player
http://m.youtube.com/watch?v=lalOy8Mbfdc&feature=youtube_gdata_player
https://www.youtube.com/watch?v=lalOy8Mbfdc&feature=youtube_gdata_player
https://youtube.com/watch?v=lalOy8Mbfdc&feature=youtube_gdata_player
https://m.youtube.com/watch?v=lalOy8Mbfdc&feature=youtube_gdata_player

http://www.youtube.com/watch?v=lalOy8Mbfdc&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655
http://youtube.com/watch?v=lalOy8Mbfdc&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655
http://m.youtube.com/watch?v=lalOy8Mbfdc&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655
https://www.youtube.com/watch?v=lalOy8Mbfdc&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655
https://youtube.com/watch?v=lalOy8Mbfdc&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655
https://m.youtube.com/watch?v=lalOy8Mbfdc&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655

http://www.youtube.com/watch?feature=player_embedded&v=lalOy8Mbfdc
http://youtube.com/watch?feature=player_embedded&v=lalOy8Mbfdc
http://m.youtube.com/watch?feature=player_embedded&v=lalOy8Mbfdc
https://www.youtube.com/watch?feature=player_embedded&v=lalOy8Mbfdc
https://youtube.com/watch?feature=player_embedded&v=lalOy8Mbfdc
https://m.youtube.com/watch?feature=player_embedded&v=lalOy8Mbfdc

http://www.youtube.com/watch?app=desktop&v=lalOy8Mbfdc
http://youtube.com/watch?app=desktop&v=lalOy8Mbfdc
http://m.youtube.com/watch?app=desktop&v=lalOy8Mbfdc
https://www.youtube.com/watch?app=desktop&v=lalOy8Mbfdc
https://youtube.com/watch?app=desktop&v=lalOy8Mbfdc
https://m.youtube.com/watch?app=desktop&v=lalOy8Mbfdc


http://www.youtube.com/watch/lalOy8Mbfdc
http://youtube.com/watch/lalOy8Mbfdc
http://m.youtube.com/watch/lalOy8Mbfdc
https://www.youtube.com/watch/lalOy8Mbfdc
https://youtube.com/watch/lalOy8Mbfdc
https://m.youtube.com/watch/lalOy8Mbfdc

http://www.youtube.com/watch/lalOy8Mbfdc?app=desktop
http://youtube.com/watch/lalOy8Mbfdc?app=desktop
http://m.youtube.com/watch/lalOy8Mbfdc?app=desktop
https://www.youtube.com/watch/lalOy8Mbfdc?app=desktop
https://youtube.com/watch/lalOy8Mbfdc?app=desktop
https://m.youtube.com/watch/lalOy8Mbfdc?app=desktop


http://www.youtube.com/v/lalOy8Mbfdc
http://youtube.com/v/lalOy8Mbfdc
http://m.youtube.com/v/lalOy8Mbfdc
https://www.youtube.com/v/lalOy8Mbfdc
https://youtube.com/v/lalOy8Mbfdc
https://m.youtube.com/v/lalOy8Mbfdc

http://www.youtube.com/v/lalOy8Mbfdc?version=3&autohide=1
http://youtube.com/v/lalOy8Mbfdc?version=3&autohide=1
http://m.youtube.com/v/lalOy8Mbfdc?version=3&autohide=1
https://www.youtube.com/v/lalOy8Mbfdc?version=3&autohide=1
https://youtube.com/v/lalOy8Mbfdc?version=3&autohide=1
https://m.youtube.com/v/lalOy8Mbfdc?version=3&autohide=1

http://www.youtube.com/v/lalOy8Mbfdc?fs=1&hl=en_US&rel=0
http://youtube.com/v/lalOy8Mbfdc?fs=1&hl=en_US&rel=0
http://m.youtube.com/v/lalOy8Mbfdc?fs=1&hl=en_US&rel=0
https://www.youtube.com/v/lalOy8Mbfdc?fs=1&amp;hl=en_US&amp;rel=0
https://www.youtube.com/v/lalOy8Mbfdc?fs=1&hl=en_US&rel=0
https://youtube.com/v/lalOy8Mbfdc?fs=1&hl=en_US&rel=0
https://m.youtube.com/v/lalOy8Mbfdc?fs=1&hl=en_US&rel=0

http://www.youtube.com/v/lalOy8Mbfdc?feature=youtube_gdata_player
http://youtube.com/v/lalOy8Mbfdc?feature=youtube_gdata_player
http://m.youtube.com/v/lalOy8Mbfdc?feature=youtube_gdata_player
https://www.youtube.com/v/lalOy8Mbfdc?feature=youtube_gdata_player
https://youtube.com/v/lalOy8Mbfdc?feature=youtube_gdata_player
https://m.youtube.com/v/lalOy8Mbfdc?feature=youtube_gdata_player


http://youtu.be/lalOy8Mbfdc
https://youtu.be/lalOy8Mbfdc

http://youtu.be/lalOy8Mbfdc?feature=youtube_gdata_player
https://youtu.be/lalOy8Mbfdc?feature=youtube_gdata_player

http://youtu.be/lalOy8Mbfdc?list=PLToa5JuFMsXTNkrLJbRlB--76IAOjRM9b
https://youtu.be/lalOy8Mbfdc?list=PLToa5JuFMsXTNkrLJbRlB--76IAOjRM9b

http://youtu.be/lalOy8Mbfdc&feature=channel
https://youtu.be/lalOy8Mbfdc&feature=channel

http://youtu.be/lalOy8Mbfdc?t=1
http://youtu.be/lalOy8Mbfdc?t=1s
https://youtu.be/lalOy8Mbfdc?t=1
https://youtu.be/lalOy8Mbfdc?t=1s

http://youtu.be/lalOy8Mbfdc?si=B_RZg_I-lLaa7UU-
https://youtu.be/lalOy8Mbfdc?si=B_RZg_I-lLaa7UU-
"""


def test_youtube_urls():
    for url in YOUTUBE_URLS.split():
        assert url_to_id(url) == "youtube=" + YOUTUBE_ID, (
            f"id {YOUTUBE_ID} not in {url!r}"
        )


def test_other_urls():
    assert (
        url_to_id("https://example.com/video.mp4")
        == r"https\=||example.com|video.mp4"
    )
