import { useEffect, useState } from "react";
import CreateJobForm from "./components/CreateJobForm";
import JobCard from "./components/JobCard";
import JobDetail from "./components/JobDetail";
import { listJobs } from "./hooks/useApi";

export default function App() {
  const [jobs, setJobs] = useState([]);
  const [view, setView] = useState("list"); // list | create | detail
  const [selectedJobId, setSelectedJobId] = useState(null);

  const fetchJobs = () => {
    listJobs()
      .then((r) => setJobs(r.jobs || []))
      .catch(() => {});
  };

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleCreated = (job) => {
    setSelectedJobId(job.id);
    setView("detail");
    fetchJobs();
  };

  return (
    <div>
      <header className="header">
        <div className="container header-inner">
          <div className="logo">
            reskin<span>.pipeline</span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {view !== "list" && (
              <button className="btn btn-secondary" onClick={() => setView("list")}>
                All Jobs
              </button>
            )}
            {view !== "create" && (
              <button className="btn btn-primary" onClick={() => setView("create")}>
                + New Skin
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="container">
        {view === "create" && (
          <CreateJobForm onCreated={handleCreated} />
        )}

        {view === "detail" && selectedJobId && (
          <JobDetail jobId={selectedJobId} onBack={() => setView("list")} />
        )}

        {view === "list" && (
          <>
            {jobs.length === 0 ? (
              <div className="empty-state">
                <h3>No reskin jobs yet</h3>
                <p>Create your first skin to get started.</p>
                <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => setView("create")}>
                  + New Skin
                </button>
              </div>
            ) : (
              <div className="jobs-grid">
                {jobs.map((job) => (
                  <JobCard key={job.id} job={job} onClick={(j) => { setSelectedJobId(j.id); setView("detail"); }} />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
