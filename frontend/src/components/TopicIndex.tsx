import { useEffect, useState } from "react";

import { api, type Category, type FAQ } from "../api/client";

interface Topic {
  category: Category;
  examples: FAQ[];
}

/** Empty state styled like a handbook's contents page: every topic, with real questions to start from. */
export function TopicIndex({ onAsk, disabled }: { onAsk: (question: string) => void; disabled: boolean }) {
  const [topics, setTopics] = useState<Topic[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.categories(), api.faqs()])
      .then(([categories, faqs]) => {
        if (cancelled) return;
        const byCategory = new Map<number, FAQ[]>();
        for (const faq of faqs.results) {
          byCategory.set(faq.category, [...(byCategory.get(faq.category) ?? []), faq]);
        }
        setTopics(
          categories.results
            .map((category) => ({ category, examples: (byCategory.get(category.id) ?? []).slice(0, 2) }))
            .filter((topic) => topic.examples.length > 0),
        );
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="welcome" aria-labelledby="welcome-title">
      <h1 id="welcome-title" className="welcome__title">
        What would you like to know?
      </h1>
      <p className="welcome__lede">
        Ask in your own words. Campus Desk looks for the closest answer in the university knowledge base and shows you
        where it came from. If it can't find one, it will say so.
      </p>

      {failed && <p className="welcome__note">Topics couldn't be loaded, but you can still type a question below.</p>}

      {topics === null && !failed && (
        <div className="contents contents--loading" aria-hidden="true">
          {Array.from({ length: 6 }, (_, index) => (
            <div key={index} className="skeleton-block" />
          ))}
        </div>
      )}

      {topics && topics.length > 0 && (
        <>
          <h2 className="contents__heading">Or start from a topic</h2>
          <ol className="contents">
            {topics.map(({ category, examples }, index) => (
              <li key={category.id} className="contents__item">
                <span className="contents__number" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3 className="contents__title">{category.name}</h3>
                  <ul className="contents__questions">
                    {examples.map((faq) => (
                      <li key={faq.id}>
                        <button type="button" className="contents__question" disabled={disabled} onClick={() => onAsk(faq.question)}>
                          {faq.question}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
