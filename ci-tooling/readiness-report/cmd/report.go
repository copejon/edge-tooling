package main

import (
	"fmt"
	"net/url"
	"path"
	"sort"
	"strings"
	"time"
)

type componentReport struct {
	Rows        []reportRow `json:"rows"`
	GeneratedAt *time.Time  `json:"generated_at"`
}

type reportRow struct {
	Component string         `json:"component"`
	Columns   []reportColumn `json:"columns"`
}

type reportColumn struct {
	RegressedTests []regressedTest `json:"regressed_tests"`
}

type regressedTest struct {
	Component  string            `json:"component"`
	TestName   string            `json:"test_name"`
	TestID     string            `json:"test_id"`
	Variants   map[string]string `json:"variants"`
	Status     int               `json:"status"`
	Regression *regression       `json:"regression"`
}

type regression struct {
	ID      int      `json:"id"`
	Triages []triage `json:"triages"`
}

type triage struct {
	ID          int      `json:"id"`
	URL         string   `json:"url"`
	Description string   `json:"description"`
	Type        string   `json:"type"`
	Bug         *bug     `json:"bug"`
	Resolved    nullTime `json:"resolved"`
}

type bug struct {
	Key string `json:"key"`
	URL string `json:"url"`
}

type nullTime struct {
	Time  time.Time `json:"Time"`
	Valid bool      `json:"Valid"`
}

type viewReport struct {
	View           string
	ViewURL        string
	GeneratedAt    *time.Time
	Regressed      int
	Untriaged      int
	Triaged        int
	Triages        []triageSummary
	UntriagedTests []untriagedTest
}

type triageSummary struct {
	ID          int
	View        string
	Tests       int
	Type        string
	Jira        string
	JiraURL     string
	TriageURL   string
	Description string
	Resolved    bool
}

type untriagedTest struct {
	View      string
	Component string
	TestName  string
	Variants  string
	Status    string
}

func buildViewReport(baseURL, view string, report componentReport, triages []triage) viewReport {
	triageByID := make(map[int]triage, len(triages))
	for _, t := range triages {
		triageByID[t.ID] = t
	}

	out := viewReport{
		View:        view,
		ViewURL:     sippyViewURL(baseURL, view),
		GeneratedAt: report.GeneratedAt,
	}

	type triageAcc struct {
		triage triage
		tests  map[string]struct{}
	}
	acc := map[int]*triageAcc{}
	seenTests := map[string]struct{}{}

	for _, row := range report.Rows {
		for _, col := range row.Columns {
			for _, test := range col.RegressedTests {
				key := testKey(test)
				if _, dup := seenTests[key]; dup {
					continue
				}
				seenTests[key] = struct{}{}
				out.Regressed++

				nested := []triage{}
				if test.Regression != nil {
					nested = test.Regression.Triages
				}
				if len(nested) == 0 {
					out.Untriaged++
					out.UntriagedTests = append(out.UntriagedTests, untriagedTest{
						View:      shortView(view),
						Component: firstNonEmpty(test.Component, row.Component),
						TestName:  test.TestName,
						Variants:  compactVariants(test.Variants),
						Status:    statusName(test.Status),
					})
					continue
				}

				out.Triaged++
				for _, nt := range nested {
					full := nt
					if richer, ok := triageByID[nt.ID]; ok {
						full = mergeTriage(nt, richer)
					}
					a, ok := acc[full.ID]
					if !ok {
						a = &triageAcc{triage: full, tests: map[string]struct{}{}}
						acc[full.ID] = a
					}
					a.tests[key] = struct{}{}
				}
			}
		}
	}

	for _, a := range acc {
		out.Triages = append(out.Triages, triageSummary{
			ID:          a.triage.ID,
			View:        shortView(view),
			Tests:       len(a.tests),
			Type:        a.triage.Type,
			Jira:        jiraKey(a.triage),
			JiraURL:     jiraURL(a.triage),
			TriageURL:   sippyTriageURL(baseURL, a.triage.ID),
			Description: a.triage.Description,
			Resolved:    a.triage.Resolved.Valid,
		})
	}
	sort.Slice(out.Triages, func(i, j int) bool {
		if out.Triages[i].Tests != out.Triages[j].Tests {
			return out.Triages[i].Tests > out.Triages[j].Tests
		}
		return out.Triages[i].ID < out.Triages[j].ID
	})
	sort.Slice(out.UntriagedTests, func(i, j int) bool {
		if out.UntriagedTests[i].Component != out.UntriagedTests[j].Component {
			return out.UntriagedTests[i].Component < out.UntriagedTests[j].Component
		}
		if out.UntriagedTests[i].TestName != out.UntriagedTests[j].TestName {
			return out.UntriagedTests[i].TestName < out.UntriagedTests[j].TestName
		}
		return out.UntriagedTests[i].Variants < out.UntriagedTests[j].Variants
	})
	return out
}

func mergeTriage(nested, full triage) triage {
	if nested.ID == 0 {
		return full
	}
	out := full
	if out.ID == 0 {
		out.ID = nested.ID
	}
	if out.URL == "" {
		out.URL = nested.URL
	}
	if out.Description == "" {
		out.Description = nested.Description
	}
	if out.Type == "" {
		out.Type = nested.Type
	}
	if out.Bug == nil {
		out.Bug = nested.Bug
	}
	if !out.Resolved.Valid {
		out.Resolved = nested.Resolved
	}
	return out
}

func testKey(t regressedTest) string {
	if t.Regression != nil && t.Regression.ID != 0 {
		return fmt.Sprintf("reg:%d", t.Regression.ID)
	}
	return strings.Join([]string{t.TestID, t.Component, t.TestName, variantString(t.Variants)}, "\x00")
}

func variantString(variants map[string]string) string {
	if len(variants) == 0 {
		return ""
	}
	parts := make([]string, 0, len(variants))
	for k, v := range variants {
		parts = append(parts, k+":"+v)
	}
	sort.Strings(parts)
	return strings.Join(parts, ",")
}

func compactVariants(variants map[string]string) string {
	if len(variants) == 0 {
		return ""
	}
	var parts []string
	for _, k := range []string{"Upgrade", "Suite", "Platform", "Topology"} {
		if v := variants[k]; v != "" {
			parts = append(parts, k+":"+v)
		}
	}
	return strings.Join(parts, ",")
}

func shortView(view string) string {
	for _, prefix := range []string{"ha-vs-"} {
		if i := strings.Index(view, prefix); i >= 0 {
			return strings.TrimPrefix(view[i:], prefix)
		}
	}
	if i := strings.Index(view, "-"); i >= 0 && i+1 < len(view) {
		return view[i+1:]
	}
	return view
}

func sippyViewURL(baseURL, view string) string {
	return strings.TrimRight(baseURL, "/") + "/sippy-ng/component_readiness/main?view=" + url.QueryEscape(view)
}

func sippyTriageURL(baseURL string, id int) string {
	return fmt.Sprintf("%s/sippy-ng/component_readiness/triages/%d", strings.TrimRight(baseURL, "/"), id)
}

func jiraKey(t triage) string {
	if t.Bug != nil && t.Bug.Key != "" {
		return t.Bug.Key
	}
	raw := t.URL
	if t.Bug != nil && t.Bug.URL != "" {
		raw = t.Bug.URL
	}
	if raw == "" {
		return ""
	}
	u, err := url.Parse(raw)
	if err != nil {
		return raw
	}
	return path.Base(u.Path)
}

func jiraURL(t triage) string {
	if t.Bug != nil && t.Bug.URL != "" {
		return t.Bug.URL
	}
	return t.URL
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if v != "" {
			return v
		}
	}
	return ""
}

func statusName(status int) string {
	switch status {
	case -1000:
		return "FailedFixed"
	case -500:
		return "Extreme"
	case -400:
		return "Significant"
	case -300:
		return "ExtremeTriaged"
	case -200:
		return "SignificantTriaged"
	case -150:
		return "Fixed"
	default:
		return fmt.Sprintf("%d", status)
	}
}

func latestGeneratedAt(reports []viewReport) string {
	var latest *time.Time
	for _, r := range reports {
		if r.GeneratedAt == nil {
			continue
		}
		if latest == nil || r.GeneratedAt.After(*latest) {
			t := *r.GeneratedAt
			latest = &t
		}
	}
	if latest == nil {
		return "unknown"
	}
	return latest.UTC().Format("2006-01-02")
}

func resolvedLabel(resolved bool) string {
	if resolved {
		return "Resolved"
	}
	return "Open"
}
