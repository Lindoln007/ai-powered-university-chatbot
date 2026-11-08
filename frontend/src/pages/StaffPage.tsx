import { useCallback, useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
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
import { TopBar } from "../components/TopBar";
import { UsageChart } from "../components/UsageChart";
import { formatDay, formatMs, formatTime, isoDate, percent } from "../lib/format";

type RangeKey = "7" | "30" | "all";
const RANGES: { key: RangeKey; label: string }[] = [
  { key: "7", label: "Last 7 days" },
  { key: "30", label: "Last 30 days" },
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
    setData((current) =>
      current && {
        ...current,
        unanswered: current.unanswered.filter((entry) => entry.id !== item.id),
        unansweredTotal: current.unansweredTotal - 1,
      },
    );
    try {
      await api.reviewUnanswered(item.id, status);
    } catch {
      void load(range);
    }
  }

  if (!ready) return <div className="app"><TopBar /></div>;

  if (!isAdmin) {
    return (
      <div className="app">
        <TopBar />
        <main className="staff staff--locked" id="main">
          <h1 className="staff__title">Staff analytics</h1>
          <p>
            {user
              ? "This page is for university staff with administrator access."
              : "Sign in with an administrator account to see how the chatbot is being used."}
          </p>
          {!user && (
            <Link to="/signin" className="button">
              Sign in
            </Link>
          )}
        </main>
      </div>
    );
  }

  const overview = data?.overview;
  const questions = overview ? overview.total_chatbot_questions - overview.small_talk_messages : 0;
  const maxCategory = Math.max(1, ...(data?.categories.categories.map((row) => row.answered_questions) ?? [1]));

  return (
    <div className="app">
      <TopBar />
      <main className="staff" id="main" aria-busy={!data && !error}>
        <header className="staff__header">
          <div>
            <h1 className="staff__title">How students are using Campus Desk</h1>
            <p className="staff__lede">Every figure is calculated from stored conversations and feedback.</p>
          </div>
          <div className="segmented" role="radiogroup" aria-label="Period">
            {RANGES.map((option) => (
              <button
                key={option.key}
                type="button"
                role="radio"
                aria-checked={range === option.key}
                className={`segmented__option${range === option.key ? " segmented__option--active" : ""}`}
                onClick={() => setRange(option.key)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </header>

        {error && (
          <div className="form-error" role="alert">
            {error}{" "}
            <button type="button" className="link-button" onClick={() => void load(range)}>
              Retry
            </button>
          </div>
        )}

        {!data && !error && <div className="skeleton-block skeleton-block--tall" aria-label="Loading analytics" />}

        {data && overview && (
          <>
            <dl className="glance">
              <div>
                <dt>Questions asked</dt>
                <dd>{questions}</dd>
              </div>
              <div>
                <dt>Answered</dt>
                <dd>
                  {percent(overview.answer_rate)}
                  <span className="glance__detail">{overview.answered_questions} questions</span>
                </dd>
              </div>
              <div>
                <dt>Not found</dt>
                <dd>
                  {overview.unanswered_questions}
                  <span className="glance__detail">{overview.clarification_requests} needed clarifying</span>
                </dd>
              </div>
              <div>
                <dt>Typical response</dt>
                <dd>
                  {formatMs(data.performance.median_response_time_ms)}
                  <span className="glance__detail">95% under {formatMs(data.performance.p95_response_time_ms)}</span>
                </dd>
              </div>
              <div>
                <dt>Feedback</dt>
                <dd>
                  <span>
                    {overview.feedback.positive} <span className="glance__unit">helpful</span> · {overview.feedback.negative}{" "}
                    <span className="glance__unit">not</span>
                  </span>
                  <span className="glance__detail">
                    {overview.feedback.total} rating{overview.feedback.total === 1 ? "" : "s"}
                  </span>
                </dd>
              </div>
            </dl>

            <section className="staff__section" aria-labelledby="trend-title">
              <h2 id="trend-title" className="staff__heading">
                Questions per day
              </h2>
              <UsageChart points={data.performance.daily} />
            </section>

            <div className="staff__columns">
              <section className="staff__section" aria-labelledby="attention-title">
                <h2 id="attention-title" className="staff__heading">
                  Needs attention <span className="count">{data.unansweredTotal}</span>
                </h2>
                <p className="staff__note">
                  Questions the chatbot couldn't answer. Add an FAQ (or an alternative wording) in Django Admin, then mark
                  the question resolved.
                </p>
                {data.unanswered.length === 0 ? (
                  <p className="empty-note">Nothing waiting. Every question in this period was answered or reviewed.</p>
                ) : (
                  <ul className="queue">
                    {data.unanswered.map((item) => (
                      <li key={item.id} className="queue__item">
                        <p className="queue__question">“{item.original_question}”</p>
                        <p className="queue__meta">
                          {formatDay(item.timestamp)}, {formatTime(item.timestamp)}
                          {item.similarity_score !== null && <> · closest match {item.similarity_score.toFixed(2)}</>}
                        </p>
                        <div className="queue__actions">
                          <a className="button button--quiet button--small" href="/admin/knowledge_base/faq/add/" target="_blank" rel="noreferrer">
                            Add FAQ <ExternalLink aria-hidden="true" size={14} />
                          </a>
                          <button type="button" className="button button--quiet button--small" onClick={() => void review(item, "resolved")}>
                            Mark resolved
                          </button>
                          <button type="button" className="link-button" onClick={() => void review(item, "dismissed")}>
                            Out of scope
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="staff__section" aria-labelledby="popular-title">
                <h2 id="popular-title" className="staff__heading">
                  Most asked
                </h2>
                {data.popular.most_frequently_answered_faqs.length === 0 ? (
                  <p className="empty-note">No answered questions in this period yet.</p>
                ) : (
                  <ol className="ranked">
                    {data.popular.most_frequently_answered_faqs.map((faq) => (
                      <li key={faq.faq_id}>
                        <span className="ranked__question">{faq.question}</span>
                        <span className="ranked__meta">
                          {faq.category} · asked {faq.times_asked}×
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </div>

            <section className="staff__section" aria-labelledby="topics-title">
              <h2 id="topics-title" className="staff__heading">
                Answers by topic
              </h2>
              {data.categories.categories.length === 0 ? (
                <p className="empty-note">No answered questions in this period yet.</p>
              ) : (
                <table className="topic-table">
                  <thead>
                    <tr>
                      <th scope="col">Topic</th>
                      <th scope="col">Answered</th>
                      <th scope="col">Avg. match</th>
                      <th scope="col">Feedback</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.categories.categories.map((row) => (
                      <tr key={row.category_id}>
                        <th scope="row">{row.category}</th>
                        <td>
                          <span className="meter" aria-hidden="true">
                            <span style={{ inlineSize: `${(row.answered_questions / maxCategory) * 100}%` }} />
                          </span>
                          {row.answered_questions}
                        </td>
                        <td>{row.average_similarity.toFixed(2)}</td>
                        <td>
                          {row.positive_feedback} helpful · {row.negative_feedback} not
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <p className="staff__footer">
              Manage FAQs, categories and verification in{" "}
              <a href="/admin/" target="_blank" rel="noreferrer">
                Django Admin <ExternalLink aria-hidden="true" size={13} />
              </a>
              .
            </p>
          </>
        )}
      </main>
    </div>
  );
}
