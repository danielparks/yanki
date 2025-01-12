# Build Anki decks from text files containing YouTube URLs

```
uv run yanki asl/lesson-01.deck
```

That will produce an `asl/lesson-01.apkg` file.

### Example deck file

```text
title: Lifeprint ASL::Phrases::Lesson 01
overlay_text: Phrase
more: rst:From `Lifeprint <https://www.lifeprint.com/>`_ ASLU `lesson 1 <https://www.lifeprint.com/asl101/lessons/lesson01.htm>`_
tags: lesson_01 phrase
audio: strip

https://www.youtube.com/watch?v=FHPszRvL9pg YOU what-NAME?
https://www.youtube.com/watch?v=UyfRF3TeLPs YOUR NAME?
https://www.youtube.com/watch?v=zW8cpOVeKZ4 DEAF YOU?
https://www.youtube.com/watch?v=xqKENRGkOUQ STUDENT YOU?
https://www.youtube.com/watch?v=OYvy_O_hhfw YOU UNDERSTAND THEM?

# You can extend a line by inserting tabs or spaces before any text:
https://www.youtube.com/watch?v=wskcwTX27RU
  INDEX-[that-person] WHO?

  (Who is that person?)
https://www.youtube.com/watch?v=l0nVGVuHHB8 AGAIN, NAME YOU?

# These cards are similar, but distinct:
https://www.youtube.com/watch?v=0Kvv6FpF348 YOUR TEACHER what-NAME?
https://www.youtube.com/watch?v=Th7pOg8YbCU YOUR TEACHER NAME WHAT?

# You can change tags used for future tags at any time:
tags: lesson_01 vocabulary extra
https://www.youtube.com/watch?v=b_qv-0Jbqn0 CLEAN-UP
```

### Note GUIDs

Anki uses the GUID (Globally Unique ID) field to identify notes for update.
Yanki generates GUIDs based on the deck ID (generated from the deck title), the
video URL, the clip of the video (e.g. `@0:01-0:02`), and the direction of the
note (e.g. `<->`).

You can customize how the GUID is generated with the `note_id` configuration:

    # Default:
    note_id: {deck_id} {url} {clip}

    # Use the text that corresponds to the video:
    note_id: {deck_id} {text}

Leaving out `{deck_id}` can be useful if you may need to move notes between
decks later on. The import will not actually move notes from one deck to
another, but it will update them in the other deck, and then you can manually
move them. This is useful if you want to keep your study progress.

If you do leave out `{deck_id}`, you should probably include something else to
make sure the GUID is unique outside of your repository.

    title: Really Cool Cards::subdeck 1
    note_id: Really Cool Cards {url} {clip}
