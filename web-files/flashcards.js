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

function note_directions(note, desired_direction) {
  const direction = query_text(note, ".metadata .direction > td > span");
  if ( direction == "->" ) {
    if ( desired_direction == "text-first" ) {
      return []; // This is a media-first note, so exclude it.
    } else {
      return ["media-first"];
    }
  } else if ( direction == "<-" ) {
    if ( desired_direction == "media-first" ) {
      return []; // This is a text-first note, so exclude it.
    } else {
      return ["text-first"];
    }
  } else {
    if ( direction != "<->" ) {
      console.error("Unknown direction for note", direction);
    }

    if ( desired_direction == "both" ) {
      return ["media-first", "text-first"];
    } else {
      return [desired_direction];
    }
  }
}

function make_card_list(notes, desired_direction) {
  var cards = [];
  notes.forEach((note) => {
    note_directions(note, desired_direction).forEach((direction) => {
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
  var filter_direction = "both", current_index = 0;
  var current_card_direction, current_card, showing_question, cards;

  function restart() {
    cards = make_card_list(document.querySelectorAll("div.note"), filter_direction);
    current_index = 0;
    finished_div.style.display = "none";

    if ( current_index >= cards.length ) {
      show_finished();
    } else {
      show_question();
    }
  }

  function hide_current() {
    if ( current_card ) {
      current_card.classList.remove(
        "question", "answer", "text-first", "media-first"
      );
    }
  }

  function set_filter_direction(direction) {
    filter_direction = direction;
    Object.values(direction_buttons).forEach((button) => {
      button.classList.remove('active');
    });
    direction_buttons[filter_direction].classList.add('active');
    restart();
  }

  function update_status() {
    var completed = current_index;
    if ( ! showing_question && current_index < cards.length ) {
      // Showing the answer, so the card is completed.
      completed++;
    }

    status_div.innerText = "Completed " + completed + " out of " + cards.length
      + " cards.";
  }

  function show_question() {
    showing_question = true;

    hide_current();
    // current_card_direction is "text-first" or "media-first".
    [current_card_direction, current_card] = cards[current_index];
    current_card.classList.remove("answer", "text-first", "media-first");
    current_card.classList.add("question", current_card_direction);

    back_button.disabled = current_index == 0;
    next_button.innerText = "Show answer";
    update_status();

    if ( current_card_direction == "media-first" ) {
      play_video(current_card);
    }
  }

  function show_answer() {
    showing_question = false;

    hide_current();
    // current_card_direction is "text-first" or "media-first".
    [current_card_direction, current_card] = cards[current_index];
    current_card.classList.remove("question", "text-first", "media-first");
    current_card.classList.add("answer", current_card_direction);

    back_button.disabled = false;
    next_button.innerText = "Next";
    update_status();

    if ( current_card_direction == "text-first" ) {
      play_video(current_card);
    }
  }

  function show_finished() {
    hide_current();
    next_button.innerText = "Restart";
    update_status();
    finished_div.style.display = "block";
  }

  function back_button_click() {
    if ( ! showing_question ) {
      show_question();
      return;
    }

    if ( current_index == 0 ) {
      // Already at the beginning.
      return;
    }

    current_index--;
    show_answer();
  }

  function next_button_click() {
    if ( current_index >= cards.length ) {
      // We ran out of cards!
      restart();
    } else if ( showing_question ) {
      show_answer();
    } else {
      // Must be showing the answer, so switch to the next card.
      current_index++;
      if ( current_index >= cards.length ) {
        show_finished();
      } else {
        show_question();
      }
    }

  }

  var direction_buttons = {
    "both": create("button", [text("Both")], {
      "id": "direction-both",
      "className": "active",
      "onclick": () => set_filter_direction("both"),
    }),
    "text-first": create("button", [text("Text")], {
      "id": "direction-text-first",
      "onclick": () => set_filter_direction("text-first"),
    }),
    "media-first": create("button", [text("Media")], {
      "id": "direction-media-first",
      "onclick": () => set_filter_direction("media-first"),
    }),
  };

  var direction_control = create("div", [
    direction_buttons["both"],
    direction_buttons["text-first"],
    direction_buttons["media-first"],
  ], { "id": "direction-control" });

  var back_button = create("button", [text("Previous")], {
    "id": "back-button",
    "onclick": back_button_click,
  });
  var next_button = create("button", [text("Flip")], {
    "id": "next-button",
    "onclick": next_button_click,
  });

  var status_div = create("div", [], { "id": "status "})
  var controls = create("div", [
    back_button,
    next_button,
    status_div,
  ], { "id": "controls" });
  var finished_div = create("div",
    [ text("Finished all cards!") ],
    { "id": "finished" });

  document.querySelector("h1").appendChild(direction_control)
  document.body.appendChild(finished_div);
  document.body.appendChild(controls);

  // Check which direction we should show the cards in.
  if ( window.location.hash ) {
    const parameters = window.location.hash.slice(1).split(":");
    if ( parameters.length > 0 ) {
      if ( direction_buttons[parameters[0]]
          && direction_buttons[parameters[0]].tagName == "BUTTON" ) {
        set_filter_direction(parameters[0]);
      }
      // For now, ignore other parameters.
    }
  }

  restart();

  document.body.addEventListener("keyup", (event) => {
    if ( event.key == " " ) {
      next_button_click();
      event.stopPropagation();
    }
  });
});
