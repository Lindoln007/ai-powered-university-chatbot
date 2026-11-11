// Small progressive enhancements. The site works fully without JavaScript.
(function () {
  document.documentElement.classList.add("js");

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var items = document.querySelectorAll(".reveal");

  if (reduced || !("IntersectionObserver" in window)) {
    items.forEach(function (item) {
      item.classList.add("is-visible");
    });
    return;
  }

  // Scroll reveal that replays every time:
  // - scrolling down, an element animates in as it enters from the bottom of the screen;
  // - scrolling up, it animates out in reverse as it leaves through the bottom;
  // - elements that leave through the top stay shown, so scrolling back up to them
  //   simply brings them back into view.
  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
        } else if (entry.boundingClientRect.top > 0) {
          entry.target.classList.remove("is-visible");
        } else {
          entry.target.classList.add("is-visible");
        }
      });
    },
    { rootMargin: "0px 0px -10% 0px", threshold: 0 }
  );

  items.forEach(function (item) {
    observer.observe(item);
  });
})();
