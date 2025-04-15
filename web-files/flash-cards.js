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
    return ["media", "text"];
  } else if ( direction == "->" ) {
    return ["media"];
  } else if ( direction == "<-" ) {
    return ["text"];
  } else {
    console.error("Unknown direction for note", direction);
    return ["media", "text"];
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
  var cards = make_card_list(document.querySelectorAll("div.note"));
  var next_button = create("button");
  var status_div = create("div", [], {"id": "status"})
  var controls = create("div", [
    next_button,
    status_div,
  ], { "id": "controls" });

  document.body.appendChild(controls);

  if ( cards.length <= 0 ) {
    return;
  }

  var current_index = 0, showing_question, direction, current;
  show_question();

  function show_question() {
     // direction is "text" or "media".
    [direction, current] = cards[current_index];
    current.classList.remove("answer", "text", "media");
    current.classList.add("question", direction);

    next_button.innerText = "Show answer";
    status_div.innerText = "Completed " + current_index + " out of "
      + cards.length + " cards.";

    if ( direction == "media" ) {
      play_video(current);
    }

    showing_question = true;
  }

  function show_answer() {
    next_button.innerText = "Next card";
    current.classList.remove("question");
    current.classList.add("answer");

    if ( direction == "text" ) {
      play_video(current);
    }

    showing_question = false;
  }

  next_button.addEventListener("click", (event) => {
    if ( showing_question ) {
      show_answer();
    } else {
      // Hide card.
      current.classList.remove("answer", "text", "media");

      // Switch to next card.
      current_index++;
      if ( !cards[current_index] ) {
        // Restart.
        cards = make_card_list(document.querySelectorAll("div.note"));
        current_index = 0;
      }

      show_question();
    }
  });
});
