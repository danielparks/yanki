function get_id(id) {
  return document.getElementById(id);
}

function create(tag, contents = [], attrs = {}) {
  var element = document.createElement(tag);
  if (typeof contents === "string") {
    element.innerHTML = contents;
  } else {
    element.append(...contents);
  }

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

function note_directions(note, desired_direction) {
  if (note.direction == "->") {
    if (desired_direction == "text-first") {
      return []; // This is a media-first note, so exclude it.
    } else {
      return ["media-first"];
    }
  } else if (note.direction == "<-") {
    if (desired_direction == "media-first") {
      return []; // This is a text-first note, so exclude it.
    } else {
      return ["text-first"];
    }
  } else {
    if (note.direction != "<->") {
      console.warn("Unknown direction for note", direction);
    }

    if (desired_direction == "both") {
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
      cards.push(new Card(note, direction));
    });
  });
  shuffle(cards);
  return cards;
}

function play_video(container) {
  container.querySelectorAll("video").forEach((video) => {
    video.controls = false;
    video.play();

    video.addEventListener("mouseenter", () => {
      video.controls = true;
    });
    video.addEventListener("mouseleave", () => {
      video.controls = false;
    });
  });
}

function fetch_json(url) {
  return fetch(url).then((response) => {
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  });
}

class Card {
  constructor(note, direction) {
    this.note = note;
    this.direction = direction;
    this._div = null;
  }

  create_in(container) {
    container.append(this.div());
  }

  remove() {
    if (this._div) {
      this._div.remove();
      this._div = null;
    }
  }

  div() {
    if (!this._div) {
      this._div = create(
        "div",
        `<div class="card ${this.direction}">
          <div class="sides">
            <h3>${this.note.text_html}</h3>
            <div class="media">${this.note.media_html}</div>
          </div>
          <div class="more">${this.note.more_html}</div>
        </div>`,
      ).children[0];
    }
    return this._div;
  }

  hide() {
    this._div.classList.remove("question", "answer");
  }

  show_question() {
    this._div.classList.remove("answer");
    this._div.classList.add("question");

    if (this.direction == "media-first") {
      play_video(this._div);
    }
  }

  show_answer() {
    this._div.classList.remove("question");
    this._div.classList.add("answer");

    if (this.direction == "text-first") {
      play_video(this._div);
    }
  }
}

function get_deck_href(path) {
  return `#path=${encodeURIComponent(path)}`;
}

window.addEventListener("load", (event) => {
  var filter_direction = "both",
    current_index = 0;
  var current_deck, current_card, showing_question, cards;

  function reset() {
    cards_div.innerHTML = "";
    current_index = 0;
    finished_div.style.display = "none";
    cards_div.append(finished_div);

    if (!current_deck || current_deck.notes.length == 0) {
      document.body.classList.add("no-cards");
      cards = [];
      show_finished();
      document.body.classList.remove("loading");
      return;
    }

    document.body.classList.remove("no-cards");
    cards = make_card_list(current_deck.notes, filter_direction);

    show_question();
  }

  function hide_current() {
    if (current_card) {
      current_card.hide();
    }
  }

  function set_filter_direction(direction) {
    filter_direction = direction;
    Object.values(direction_buttons).forEach((button) => {
      button.classList.remove("active");
    });
    direction_buttons[filter_direction].classList.add("active");
  }

  function filter_direction_click(direction) {
    set_filter_direction(direction);
    reset();
  }

  function update_status() {
    var completed = current_index;
    if (!showing_question && current_index < cards.length) {
      // Showing the answer, so the card is completed.
      completed++;
    }

    status_div.innerText =
      "Completed " + completed + " out of " + cards.length + " cards.";
  }

  // Make sure only a certain range of cards have <div>s on the page so that we
  // don’t keep too many <video> elements on-page at the same time.
  //
  // This also makes sure the current_card has a <div>.
  //
  // If first_index is smaller than 0, or last_index is past the end of the
  // array, this will treat them like 0 or length-1, respectively.
  function ensure_card_divs(first_index, last_index) {
    cards.forEach((card, i) => {
      if ((i >= first_index && i <= last_index) || card == current_card) {
        card.create_in(cards_div);
      } else {
        card.remove();
      }
    });
  }

  function show_question() {
    showing_question = true;

    back_button.disabled = current_index == 0;
    next_button.innerText = "Show answer";
    update_status();

    ensure_card_divs(current_index, current_index + 3);
    hide_current();
    current_card = cards[current_index];
    current_card.show_question();
    document.body.classList.remove("loading");
  }

  function show_answer() {
    showing_question = false;

    back_button.disabled = false;
    next_button.innerText = "Next";
    update_status();

    ensure_card_divs(current_index - 3, current_index);
    hide_current();
    current_card = cards[current_index];
    current_card.show_answer();
    document.body.classList.remove("loading");
  }

  function show_finished() {
    hide_current();
    next_button.innerText = "Restart";
    update_status();
    finished_div.style.display = "block";
  }

  function back_button_click() {
    if (!showing_question) {
      show_question();
      return;
    }

    if (current_index == 0) {
      // Already at the beginning.
      return;
    }

    current_index--;
    show_answer();
  }

  function next_button_click() {
    if (current_index >= cards.length) {
      // We ran out of cards!
      reset();
    } else if (showing_question) {
      show_answer();
    } else {
      // Must be showing the answer, so switch to the next card.
      current_index++;
      if (current_index >= cards.length) {
        show_finished();
      } else {
        show_question();
      }
    }
  }

  function fix_param_direction(param, fallback) {
    if (param) {
      if (
        direction_buttons[param] &&
        direction_buttons[param].tagName == "BUTTON"
      ) {
        return param;
      } else {
        console.warn("Invalid direction parameter:", param);
      }
    }
    return fallback;
  }

  function parse_hash(hash) {
    const params = new URLSearchParams(hash.slice(1));
    return {
      path: params.get("path"),
      direction: fix_param_direction(params.get("direction"), filter_direction),
    };
  }

  function directory_deck_click(_event) {
    load_params(parse_hash(this.hash));
  }

  function load_params(params) {
    /* Mark correct directory entry as current */
    directory.querySelectorAll("a").forEach((a) => {
      a.classList.remove("current");
    });
    var current = directory
      .querySelectorAll(`a[href="${get_deck_href(params.path)}"]`)
      .forEach((a) => {
        a.classList.add("current");
      });

    set_filter_direction(params.direction);
    if (params.path) {
      document.body.classList.add("loading");
      document.body.classList.remove("no-deck");
      fetch_json(params.path).then((deck) => {
        current_deck = deck;
        title.innerText = deck.title.replace(/.*::/, "");
        reset();
      });
    } else {
      document.body.classList.add("no-deck");
      current_deck = null;
      reset();
    }
  }

  function trees_to_ol(nodes) {
    return create("ol", nodes.map((node) => {
      var name_label = text(node.segment);
      if (node.path) {
        name_label = create("a", [name_label], {
          href: get_deck_href(node.path),
          onclick: directory_deck_click,
        });
      } else {
        name_label = create("span", [name_label]);
      }

      if (node.children) {
        return create("li", [
          name_label,
          trees_to_ol(node.children),
        ]);
      } else {
        return create("li", [ name_label ]);
      }
    }));
  }

  document
    .querySelector("#viewer > main > header > a")
    .addEventListener("click", (_) => {
      load_params(parse_hash("#"));
    });

  var directory = document.querySelector("#directory > main");
  directory.append(trees_to_ol(JSON.parse(get_id("decks-json").innerText)));

  var title = get_id("title");

  var direction_buttons = {};
  document.querySelectorAll("#direction-control button").forEach((button) => {
    var direction = button.id.replace("direction-", "");
    button.addEventListener("click", () => filter_direction_click(direction));
    direction_buttons[direction] = button;
  });

  var finished_div = get_id("finished");
  var cards_div = get_id("cards");

  var back_button = get_id("back-button");
  back_button.addEventListener("click", back_button_click);
  var next_button = get_id("next-button");
  next_button.addEventListener("click", next_button_click);

  var status_div = get_id("status");

  // Check which direction we should show the cards in.
  if (window.location.hash) {
    load_params(parse_hash(window.location.hash));
  } else {
    load_params(parse_hash("#"));
  }

  document.body.addEventListener("keyup", (event) => {
    if (event.key == " ") {
      next_button_click();
      event.stopPropagation();
    }
  });
});
