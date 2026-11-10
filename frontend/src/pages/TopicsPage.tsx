import { useEffect, useMemo, useState } from "react";
import { ChevronDown, MessageCircle, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { api, type Category, type FAQ } from "../api/client";
import { AppShell } from "../components/AppShell";
import { paragraphs } from "../lib/format";
import { topicIcon, topicRank } from "../lib/topics";

/** Every published answer, grouped by topic, for people who would rather read than chat. */
export function TopicsPage() {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<Category[]>([]);
  const [faqs, setFaqs] = useState<FAQ[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [filter, setFilter] = useState("");
  const [topic, setTopic] = useState<number | "all">("all");

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.categories(), api.faqs()])
      .then(([categoryPage, faqPage]) => {
        if (cancelled) return;
        setCategories([...categoryPage.results].sort((a, b) => topicRank(a.slug) - topicRank(b.slug)));
        setFaqs(faqPage.results);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const groups = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return categories
      .filter((category) => topic === "all" || category.id === topic)
      .map((category) => ({
        category,
        items: (faqs ?? []).filter(
          (faq) =>
            faq.category === category.id &&
            (!needle || faq.question.toLowerCase().includes(needle) || faq.answer.toLowerCase().includes(needle)),
        ),
      }))
      .filter((group) => group.items.length > 0);
  }, [categories, faqs, filter, topic]);

  const counts = useMemo(() => {
    const map = new Map<number, number>();
    for (const faq of faqs ?? []) map.set(faq.category, (map.get(faq.category) ?? 0) + 1);
    return map;
  }, [faqs]);

  return (
    <AppShell>
      <div className="scrollarea">
        <div className="page">
          <header className="page__head">
            <h1>Browse topics</h1>
            <p>Every answer in the knowledge base, grouped by topic. Open one to read it, or continue it in the chat.</p>
          </header>

          <div className="filterbar">
            <div className="searchfield">
              <Search aria-hidden="true" size={18} />
              <label htmlFor="topic-filter" className="sr-only">
                Filter answers
              </label>
              <input
                id="topic-filter"
                type="search"
                placeholder="Filter by word, e.g. hostel"
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
              />
            </div>
            <div className="pillrow" role="group" aria-label="Topic">
              <button type="button" className="pill" aria-pressed={topic === "all"} onClick={() => setTopic("all")}>
                All <span>{faqs?.length ?? 0}</span>
              </button>
              {categories
                .filter((category) => counts.get(category.id))
                .map((category) => (
                  <button
                    key={category.id}
                    type="button"
                    className="pill"
                    aria-pressed={topic === category.id}
                    onClick={() => setTopic(category.id)}
                  >
                    {category.name} <span>{counts.get(category.id)}</span>
                  </button>
                ))}
            </div>
          </div>

          {failed && <p className="notice-card">Answers couldn't be loaded. Check your connection and reload the page.</p>}

          {faqs === null && !failed && (
            <div className="faqlist" aria-hidden="true">
              <span className="skeleton skeleton--row" />
              <span className="skeleton skeleton--row" />
              <span className="skeleton skeleton--row" />
            </div>
          )}

          {faqs !== null && groups.length === 0 && (
            <div className="notice-card">
              <h2>No answers match “{filter.trim()}”</h2>
              <p>Try a different word, or ask the question in the chat. Unanswered questions are reviewed by staff.</p>
              <button type="button" className="btn btn--primary" onClick={() => navigate("/", { state: { ask: filter.trim() } })}>
                <MessageCircle aria-hidden="true" size={17} />
                Ask in chat
              </button>
            </div>
          )}

          {groups.map(({ category, items }) => {
            const Icon = topicIcon(category.slug);
            return (
              <section key={category.id} className="faqgroup" aria-labelledby={`topic-${category.id}`}>
                <h2 id={`topic-${category.id}`}>
                  <Icon aria-hidden="true" size={20} />
                  {category.name}
                </h2>
                <div className="faqlist">
                  {items.map((faq) => (
                    <details key={faq.id} className="faq">
                      <summary>
                        <span>{faq.question}</span>
                        <ChevronDown aria-hidden="true" size={18} />
                      </summary>
                      <div className="faq__body">
                        {paragraphs(faq.answer).map((text, index) => (
                          <p key={index}>{text}</p>
                        ))}
                        <div className="faq__foot">
                          {faq.information_type === "demonstration" && <span className="chip chip--demo">Demo information</span>}
                          <span className="faq__ref">{faq.reference_code}</span>
                          <button
                            type="button"
                            className="btn btn--soft btn--sm"
                            onClick={() => navigate("/", { state: { ask: faq.question } })}
                          >
                            <MessageCircle aria-hidden="true" size={15} />
                            Ask in chat
                          </button>
                        </div>
                      </div>
                    </details>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
}
