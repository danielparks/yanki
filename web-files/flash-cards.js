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
  var next_button = create("button", [ text("next") ]);
  var controls = create("div", [
    text("Found " + cards.length + " cards"),
    next_button,
  ], {"id": "controls"});

  document.body.appendChild(controls);

  if ( cards.length <= 0 ) {
    return;
  }

  // List all cards to console.
  cards.forEach(([direction, note]) => {
    console.log(direction, query_text(note, "h3"));
  });

  var current_index = 0;
  var [direction, current] = cards[current_index];
  current.classList.add("question", direction);

  next_button.addEventListener("click", (event) => {
    if ( !current.classList.replace("question", "answer") ) {
      // Move to the next card.
      current.classList.remove("answer", "text", "media");
      current_index++;
      if ( !cards[current_index] ) {
        alert("All done.");
      } else {
        [direction, current] = cards[current_index];
        current.classList.remove("answer", "text", "media");
        current.classList.add("question", direction);
      }
    }
  });
});
