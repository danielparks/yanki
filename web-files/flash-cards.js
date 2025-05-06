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

  function hide_current() {
    if ( current ) {
      current.classList.remove(
        "question", "answer", "text-first", "media-first"
      );
    }
  }

  function update_status() {
    var filter = direction_select.value, completed = 0, count = 0;
    if ( filter == "both" ) {
      count = cards.length;
      completed = current_index;
    } else {
      var i = 0;
      for ( ; i < current_index ; i++ ) {
        if ( cards[i][0] == filter ) {
          completed++;
          count++;
        }
      }
      for ( ; i < cards.length ; i++ ) {
        if ( cards[i][0] == filter ) {
          count++;
        }
      }
    }

    if ( ! showing_question && current_index < cards.length ) {
      // Showing the answer, so the card is completed.
      completed++;
    }

    status_div.innerText = "Completed " + completed + " out of " + count
      + " cards.";
  }

  function show_question() {
    showing_question = true;

    hide_current();
    // direction is "text-first" or "media-first".
    [direction, current] = cards[current_index];
    current.classList.remove("answer", "text-first", "media-first");
    current.classList.add("question", direction);

    next_button.innerText = "Show answer";
    update_status();

    if ( direction == "media-first" ) {
      play_video(current);
    }
  }

  function show_answer() {
    showing_question = false;

    current.classList.remove("question");
    current.classList.add("answer");
    next_button.innerText = "Next card";
    update_status();

    if ( direction == "text-first" ) {
      play_video(current);
    }
  }

  function show_finished() {
    hide_current();
    next_button.innerText = "Restart";
    update_status();
    finished_div.style.display = "block";
  }

  // Find the card that matches direction_select at or beyond current_index.
  function find_next_card() {
    var advanced = false;
    if ( direction_select.value == "both" ) {
      // No need to filter.
      return advanced;
    }

    for ( ; current_index < cards.length ; current_index++ ) {
      if ( cards[current_index][0] == direction_select.value ) {
        // An acceptable card. Show it.
        return advanced;
      }
      advanced = true;
    }

    return advanced;
  }

  function direction_select_change() {
    if ( find_next_card() ) {
      // The shown card was filtered, so move to the next acceptable one.
      if ( current_index >= cards.length ) {
        show_finished();
      } else {
        show_question();
      }
    } else {
      update_status();
    }
  }

  function next_button_click() {
    if ( current_index >= cards.length ) {
      // We ran out of cards!
      restart();
      // Fall through to show card.
    } else if ( showing_question ) {
      show_answer();
      return;
    } else {
      // Must be showing the answer, so hide the old card...
      current.classList.remove("answer", "text-first", "media-first");

      // ... and switch to the next card.
      current_index++;
      // Fall through to show card.
    }

    find_next_card();
    if ( current_index >= cards.length ) {
      show_finished();
    } else {
      show_question();
    }
  }

  var next_button = create("button", []);
  var direction_select = create("select", [
    create("option", [text("Mix of text and media first")], { "value": "both" }),
    create("option", [text("Text first")], { "value": "text-first" }),
    create("option", [text("Media first")], { "value": "media-first" }),
  ], { "onchange": direction_select_change });
  var status_div = create("div", [], { "id": "status "})
  var controls = create("div", [
    direction_select,
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
