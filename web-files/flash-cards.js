function get_id(id) {
  return document.getElementById(id);
}

function create(tag, contents=[], attrs={}) {
  var element = document.createElement(tag);
  contents.forEach((child) => element.appendChild(child));
  for (var key in attrs) {
    element[key] = attrs[key];
  }
  return element;
}

function text(contents) {
  return document.createTextNode(contents);
}

// From https://stackoverflow.com/a/12646864/1043949 by Laurens Holst
function shuffle(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
}

function query_text(element, query) {
  return element.querySelector(query).innerText;
}

function note_direction(note) {
  const direction = query_text(note, ".metadata .direction > td > span");
  if ( direction == "<->" ) {
    return ["media-first", "text-first"];
  } else if ( direction == "->" ) {
    return ["media-first"];
  } else if ( direction == "<-" ) {
    return ["text-first"];
  } else {
    console.error("Unknown direction for note", direction);
    return ["media-first", "text-first"];
  }
}

function make_card_list(notes) {
  var cards = [];
  notes.forEach((note) => {
    note_direction(note).forEach((direction) => {
      cards.push([direction, note]);
    });
  });
  shuffle(cards);
  return cards;
}

function play_video(container) {
    container.querySelectorAll("video").forEach((video) => {
      video.controls = false;
      video.play();

      video.addEventListener("mouseenter", () => { video.controls = true; });
      video.addEventListener("mouseleave", () => { video.controls = false; });
    });
}

window.addEventListener("load", (event) => {
  function restart() {
    cards = make_card_list(document.querySelectorAll("div.note"));
    current_index = 0;
    finished_div.style.display = "none";
  }

  function show_question() {
     // direction is "text-first" or "media-first".
    [direction, current] = cards[current_index];
    current.classList.remove("answer", "text-first", "media-first");
    current.classList.add("question", direction);

    next_button.innerText = "Show answer";
    status_div.innerText = "Completed " + current_index + " out of "
      + cards.length + " cards.";

    if ( direction == "media-first" ) {
      play_video(current);
    }

    showing_question = true;
  }

  function show_answer() {
    next_button.innerText = "Next card";
    current.classList.remove("question");
    current.classList.add("answer");

    if ( direction == "text-first" ) {
      play_video(current);
    }

    showing_question = false;
  }

  function show_finished() {
    current.classList.remove("question", "answer", "text-first", "media-first");
    next_button.innerText = "Restart";
    status_div.innerText = "Completed " + current_index + " out of "
      + cards.length + " cards.";
    finished_div.style.display = "block";
  }

  function next_button_click() {
    if ( current_index >= cards.length ) {
      // We ran out of cards!
      restart();
      show_question();
    } else if ( showing_question ) {
      show_answer();
    } else {
      // Must be showing the answer, so hide the old card...
      current.classList.remove("answer", "text-first", "media-first");

      // ... and switch to the next card.
      current_index++;
      if ( current_index >= cards.length ) {
        show_finished();
      } else {
        show_question();
      }
    }
  }

  var next_button = create("button", []);
  var status_div = create("div", [], { "id": "status "})
  var controls = create("div", [
    next_button,
    status_div,
  ], { "id": "controls" });
  var finished_div = create("div",
    [ text("Finished all cards!") ],
    { "id": "finished" });

  document.body.appendChild(finished_div);
  document.body.appendChild(controls);

  var current_index = 0, showing_question, direction, current, cards;
  restart();

  if ( cards.length <= 0 ) {
    return;
  }

  show_question();

  next_button.addEventListener("click", next_button_click);
  document.body.addEventListener("keyup", (event) => {
    if ( event.key == " " ) {
      next_button_click();
      event.stopPropagation();
    }
  });
});
