# Build Anki decks from text files containing YouTube URLs

```
poetry install
poetry run yanki asl/lesson-01.deck
```

That will produce an `asl/lesson-01.apkg` file.

### Example deck file

```text
title: Lifeprint ASL::Phrases::Lesson 01
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
