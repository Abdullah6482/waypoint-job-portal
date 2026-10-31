# Task 5 — Waypoint Job Portal feature screenshots

The captures use fictional names, `example.test` email addresses, portfolio URLs, jobs, and applications. They were created in a separate temporary SQLite database under `%LOCALAPPDATA%\Temp\waypoint-task5-submission-demo-20261031-1248`; the project's normal `instance\jobs.sqlite3` was not changed. The employer-posted demo listing and submitted application are also confined to that temporary database.

| Screenshot | Feature shown |
|---|---|
| `01-job-marketplace-overview.png` | Public job marketplace, open listings, search fields, and filter controls |
| `02-search-by-keyword.png` | Keyword search across role listings |
| `03-search-by-location.png` | Location search |
| `04-filter-by-work-type.png` | Work-type filter; available types are Full-time, Part-time, Contract, Internship, and Remote |
| `05-filter-by-category.png` | Category filter; available categories are Engineering, Design, Product, Marketing, Customer Support, Operations, Finance, and Other |
| `06-empty-search-results.png` | No-results state and clear-search path |
| `07-open-job-detail-as-guest.png` | Open job detail, salary range, role description, and sign-in-to-apply prompt |
| `08-closed-listing-detail.png` | Closed listing and notice that applications are no longer accepted |
| `09-login-form.png` | Sign-in form |
| `10-seeker-registration-form.png` | Job-seeker registration form and password-length guidance |
| `11-employer-registration-form.png` | Employer registration with the company-name field enabled |
| `12-seeker-application-form.png` | Authenticated seeker application form with optional resume/portfolio URL and cover letter |
| `13-application-form-filled.png` | Application fields populated with fictional information before submission |
| `14-application-submitted.png` | Application confirmation on the role detail page |
| `15-seeker-application-dashboard.png` | Seeker dashboard tracking applications and Pending, Reviewing, and Accepted statuses |
| `16-employer-hiring-dashboard.png` | Employer listings, application counts, candidate notes, portfolio links, and review controls |
| `17-create-job-form-empty.png` | New listing form and supported work-type/category controls |
| `18-create-job-form-filled.png` | Job details, location, type, category, annual salary range, and description before publishing |
| `19-job-posted-confirmation.png` | Successful publishing and updated employer listings |
| `20-edit-job-and-listing-status.png` | Pre-filled edit form, salary and description fields, and open/closed listing status |
| `21-employer-application-review.png` | Saving an application status change; statuses are Pending, Reviewing, Accepted, and Rejected |
| `22-admin-platform-dashboard.png` | Platform statistics, account moderation table, and latest job listings |
| `23-admin-account-moderation.png` | Deactivation feedback and inactive-account state for a synthetic member |
| `24-responsive-mobile-job-search.png` | Mobile marketplace, category filter, and responsive job cards |
| `25-employer-rejected-application-state.png` | Employer saving the Rejected application status; all four application statuses are represented across the set |

The screenshots show controls available in the rendered app. Although a job-deletion route exists in the backend, the current employer pages do not render a delete control, so deletion is not presented as a user-facing feature here. Resume/portfolio information is collected as a link; the app does not upload resume files.
