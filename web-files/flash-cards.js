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

  var current_index = 0;
  var [direction, current] = cards[current_index];
  current.classList.add("question", direction);
  update_controls(true);

  function update_controls(on_question) {
    if ( on_question ) {
      next_button.innerText = "Show answer";
      status_div.innerText = "Completed " + current_index + " out of "
        + cards.length + " cards.";
    } else {
      next_button.innerText = "Next card";
    }
  }

  next_button.addEventListener("click", (event) => {
    if ( !current.classList.replace("question", "answer") ) {
      // Show question of next card.
      current.classList.remove("answer", "text", "media");
      current_index++;

      if ( !cards[current_index] ) {
        // Restart.
        cards = make_card_list(document.querySelectorAll("div.note"));
        current_index = 0;
      }

      update_controls(true);

      [direction, current] = cards[current_index];
      current.classList.remove("answer", "text", "media");
      current.classList.add("question", direction);
    } else {
      // Show answer of current card.
      update_controls(false);
    }
  });
});
