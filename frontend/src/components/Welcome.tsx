import { useEffect, useState, type ReactNode } from "react";
import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";

import { api, type Category, type FAQ } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { topicIcon, topicRank } from "../lib/topics";
import { Horizon } from "./Brand";

interface Topic {
  category: Category;
  examples: FAQ[];
  total: number;
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

interface Props {
  composer: ReactNode;
  onAsk: (question: string) => void;
  disabled: boolean;
}

/** First screen: greeting, the question box, and a tiled index of topics with real questions to tap. */
export function Welcome({ composer, onAsk, disabled }: Props) {
  const { user } = useAuth();
  const [topics, setTopics] = useState<Topic[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.categories(), api.faqs()])
      .then(([categories, faqs]) => {
        if (cancelled) return;
        const byCategory = new Map<number, FAQ[]>();
        for (const faq of faqs.results) byCategory.set(faq.category, [...(byCategory.get(faq.category) ?? []), faq]);
        setTopics(
          categories.results
            .map((category) => {
              const all = byCategory.get(category.id) ?? [];
              return { category, examples: all.slice(0, 3), total: all.length };
            })
            .filter((topic) => topic.total > 0)
            .sort((a, b) => topicRank(a.category.slug) - topicRank(b.category.slug)),
        );
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const name = user?.first_name || (user ? user.username : "");

  return (
    <div className="welcome">
      <Horizon />
      <section className="hero" aria-labelledby="hero-title">
        <p className="hero__kicker">
          {greeting()}
          {name ? `, ${name}` : ""}
        </p>
        <h1 id="hero-title" className="hero__title">
          What can I help you find?
        </h1>
        <p className="hero__lede">
          Ask in your own words. I search the university knowledge base, show you the source, and tell you plainly when
          I don't have an answer.
        </p>
        <div className="hero__composer">{composer}</div>
      </section>

      <section className="topics" aria-labelledby="topics-title">
        <div className="topics__head">
          <h2 id="topics-title">Popular topics</h2>
          <Link to="/topics" className="inline-link">
            Browse all answers <ArrowUpRight aria-hidden="true" size={15} />
          </Link>
        </div>

        {failed && <p className="topics__note">Topics couldn't be loaded, but you can still type a question above.</p>}

        {topics === null && !failed && (
          <div className="bento" aria-hidden="true">
            {Array.from({ length: 5 }, (_, index) => (
              <div key={index} className={`tile tile--skeleton${index < 2 ? " tile--feature" : ""}`} />
            ))}
          </div>
        )}

        {topics && (
          <ul className="bento">
            {topics.map(({ category, examples, total }, index) => {
              const Icon = topicIcon(category.slug);
              const feature = index < 2;
              return (
                <li key={category.id} className={`tile${feature ? " tile--feature" : ""}`}>
                  <div className="tile__head">
                    <Icon aria-hidden="true" size={feature ? 22 : 18} />
                    <h3>{category.name}</h3>
                    <span className="tile__count">{total}</span>
                  </div>
                  <ul className="tile__questions">
                    {examples.slice(0, feature ? 3 : 1).map((faq) => (
                      <li key={faq.id}>
                        <button type="button" disabled={disabled} onClick={() => onAsk(faq.question)}>
                          {faq.question}
                        </button>
                      </li>
                    ))}
                  </ul>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
