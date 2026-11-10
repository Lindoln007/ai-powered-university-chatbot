import { useCallback, useEffect, useState } from "react";
import { ExternalLink, Inbox } from "lucide-react";
import { Link } from "react-router-dom";

import {
  api,
  ApiError,
  type CategoryStatistics,
  type Overview,
  type Performance,
  type PopularQuestions,
  type UnansweredQuestion,
} from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { Ring, UsageChart } from "../components/Charts";
import { useToast } from "../components/Toast";
import { formatDay, formatMs, formatTime, isoDate } from "../lib/format";

type RangeKey = "7" | "30" | "all";
const RANGES: { key: RangeKey; label: string }[] = [
  { key: "7", label: "7 days" },
  { key: "30", label: "30 days" },
  { key: "all", label: "All time" },
];

function rangeParams(key: RangeKey) {
  if (key === "all") return {};
  const start = new Date();
  start.setDate(start.getDate() - (Number(key) - 1));
  return { start_date: isoDate(start) };
}

interface Data {
  overview: Overview;
  performance: Performance;
  popular: PopularQuestions;
  categories: CategoryStatistics;
  unanswered: UnansweredQuestion[];
  unansweredTotal: number;
}

export function StaffPage() {
  const { user, ready, isAdmin } = useAuth();
  const toast = useToast();
  const [range, setRange] = useState<RangeKey>("30");
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (key: RangeKey) => {
    const params = rangeParams(key);
    setError(null);
    try {
      const [overview, performance, popular, categories, unanswered] = await Promise.all([
        api.overview(params),
        api.performance(params),
        api.popular(params),
        api.categoryStats(params),
        api.unanswered(params),
      ]);
      setData({ overview, performance, popular, categories, unanswered: unanswered.results, unansweredTotal: unanswered.count });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Analytics couldn't be loaded.");
    }
  }, []);

  useEffect(() => {
    if (isAdmin) void load(range);
  }, [isAdmin, range, load]);

  async function review(item: UnansweredQuestion, status: "resolved" | "dismissed") {
    setData(
      (current) =>
        current && {
          ...current,
          unanswered: current.unanswered.filter((entry) => entry.id !== item.id),
          unansweredTotal: current.unansweredTotal - 1,
        },
    );
    try {
      await api.reviewUnanswered(item.id, status);
      toast(status === "resolved" ? "Marked as resolved" : "Marked as out of scope");
    } catch {
      toast("Couldn't save that. Reloading.");
      void load(range);
    }
  }

  if (!ready) return <AppShell>{null}</AppShell>;

  if (!isAdmin) {
    return (
      <AppShell>
        <div className="scrollarea">
          <div className="page">
            <div className="notice-card">
              <h1>Staff dashboard</h1>
              <p>
                {user
                  ? "This page is for university staff with administrator access."
                  : "Sign in with an administrator account to see how the chatbot is being used."}
              </p>
              {!user && (
                <Link to="/signin" className="btn btn--primary">
                  Sign in
                </Link>
              )}
            </div>
          </div>
        </div>
      </AppShell>
    );
  }

  const overview = data?.overview;
  const questions = overview ? overview.total_chatbot_questions - overview.small_talk_messages : 0;
  const topics = data?.categories.categories ?? [];
  const maxTopic = Math.max(1, ...topics.map((row) => row.answered_questions));
  const feedback = overview?.feedback;
  const helpfulShare = feedback && feedback.total > 0 ? feedback.positive / feedback.total : 0;

  return (
    <AppShell>
      <div className="scrollarea">
        <div className="page page--wide" aria-busy={!data && !error}>
          <header className="page__head page__head--split">
            <div>
              <h1>Staff dashboard</h1>
              <p>How students are using Campus Desk. Every figure comes from stored conversations and feedback.</p>
            </div>
            <div className="segmented" role="radiogroup" aria-label="Period">
              {RANGES.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  role="radio"
                  aria-checked={range === option.key}
                  className={range === option.key ? "is-active" : ""}
                  onClick={() => setRange(option.key)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </header>

          {error && (
            <div className="form__error" role="alert">
              {error}{" "}
              <button type="button" className="inline-link" onClick={() => void load(range)}>
                Retry
              </button>
            </div>
          )}

          {!data && !error && <span className="skeleton skeleton--dash" aria-label="Loading analytics" />}

          {data && overview && (
            <div className="dash">
              <section className="panel panel--rate" aria-labelledby="rate-title">
                <Ring value={overview.answer_rate} label="Questions answered" />
                <div>
                  <h2 id="rate-title">Questions answered</h2>
                  <p className="panel__big">
                    {overview.answered_questions} <span>of {questions}</span>
                  </p>
                  <p className="panel__sub">
                    {overview.unanswered_questions} not found · {overview.clarification_requests} needed clarifying
                  </p>
                </div>
              </section>

              <section className="panel panel--stat" aria-label="Conversations">
                <h2>Conversations</h2>
                <p className="panel__big">{overview.total_conversations}</p>
                <p className="panel__sub">{overview.total_registered_users} registered users</p>
              </section>

              <section className="panel panel--stat" aria-label="Typical response time">
                <h2>Typical response</h2>
                <p className="panel__big">{formatMs(data.performance.median_response_time_ms)}</p>
                <p className="panel__sub">95% under {formatMs(data.performance.p95_response_time_ms)}</p>
              </section>

              <section className="panel panel--stat" aria-label="Feedback">
                <h2>Feedback</h2>
                {feedback && feedback.total > 0 ? (
                  <>
                    <p className="panel__big">
                      {Math.round(helpfulShare * 100)}% <span>helpful</span>
                    </p>
                    <div className="splitbar" aria-hidden="true">
                      <i style={{ inlineSize: `${helpfulShare * 100}%` }} />
                    </div>
                    <p className="panel__sub">
                      {feedback.positive} helpful · {feedback.negative} not · {feedback.total} rating{feedback.total === 1 ? "" : "s"}
                    </p>
                  </>
                ) : (
                  <p className="panel__sub">No ratings in this period yet.</p>
                )}
              </section>

              <section className="panel panel--chart" aria-labelledby="trend-title">
                <h2 id="trend-title">Questions per day</h2>
                <UsageChart points={data.performance.daily} />
              </section>

              <section className="panel panel--queue" aria-labelledby="queue-title">
                <h2 id="queue-title">
                  Needs attention <span className="count">{data.unansweredTotal}</span>
                </h2>
                <p className="panel__sub">Questions the chatbot couldn't answer. Add an FAQ in Django Admin, then mark it resolved.</p>
                {data.unanswered.length === 0 ? (
                  <div className="empty">
                    <Inbox aria-hidden="true" size={28} />
                    <p>Nothing waiting. Every question in this period was answered or reviewed.</p>
                  </div>
                ) : (
                  <ul className="queue">
                    {data.unanswered.map((item) => (
                      <li key={item.id}>
                        <p className="queue__q">“{item.original_question}”</p>
                        <p className="queue__meta">
                          {formatDay(item.timestamp)}, {formatTime(item.timestamp)}
                          {item.similarity_score !== null && <> · closest match {item.similarity_score.toFixed(2)}</>}
                        </p>
                        <div className="queue__actions">
                          <a className="btn btn--soft btn--sm" href="/admin/knowledge_base/faq/add/" target="_blank" rel="noreferrer">
                            Add FAQ <ExternalLink aria-hidden="true" size={14} />
                          </a>
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => void review(item, "resolved")}>
                            Resolved
                          </button>
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => void review(item, "dismissed")}>
                            Out of scope
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="panel panel--popular" aria-labelledby="popular-title">
                <h2 id="popular-title">Most asked</h2>
                {data.popular.most_frequently_answered_faqs.length === 0 ? (
                  <p className="panel__sub">No answered questions in this period yet.</p>
                ) : (
                  <ol className="ranked">
                    {data.popular.most_frequently_answered_faqs.map((faq) => (
                      <li key={faq.faq_id}>
                        <span className="ranked__q">{faq.question}</span>
                        <span className="ranked__meta">
                          {faq.category} · {faq.times_asked}×
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              <section className="panel panel--topics" aria-labelledby="topics-title">
                <h2 id="topics-title">Answers by topic</h2>
                {topics.length === 0 ? (
                  <p className="panel__sub">No answered questions in this period yet.</p>
                ) : (
                  <ul className="bars">
                    {topics.map((row) => (
                      <li key={row.category_id}>
                        <span className="bars__label">{row.category}</span>
                        <span className="bars__track" aria-hidden="true">
                          <i style={{ inlineSize: `${(row.answered_questions / maxTopic) * 100}%` }} />
                        </span>
                        <span className="bars__value">{row.answered_questions}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="panel__sub">
                  Manage FAQs and verification in{" "}
                  <a href="/admin/" target="_blank" rel="noreferrer" className="inline-link">
                    Django Admin <ExternalLink aria-hidden="true" size={13} />
                  </a>
                </p>
              </section>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
