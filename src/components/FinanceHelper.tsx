"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  Tooltip,
  CartesianGrid,
  XAxis,
  YAxis,
  Legend,
  AreaChart,
  Area,
} from "recharts";
import { toast } from "sonner";
import { createUser, getUsage as apiGetUsage, simulateScenario, exportReport, getPathwayLive } from "@/lib/api";

// Utility helpers
const currency = (n: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(n);

const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n));

export default function FinanceHelper() {
  // Inputs
  const [employees, setEmployees] = useState<number>(3);
  const [salary, setSalary] = useState<number>(50000);
  const [marketing, setMarketing] = useState<number>(75000);
  const [price, setPrice] = useState<number>(999);
  const [cash, setCash] = useState<number>(1_000_000); // starting cash reserve

  // Live data feed toggle (Pathway)
  const [pathwayConnected, setPathwayConnected] = useState<boolean>(false);

  // Usage counters (from backend)
  const [scenarioCount, setScenarioCount] = useState<number>(0);
  const [reportCount, setReportCount] = useState<number>(0);

  // User handling
  const [userId, setUserId] = useState<string | null>(null);
  const [bootstrapping, setBootstrapping] = useState<boolean>(true);

  // Loading flags
  const [simulating, setSimulating] = useState<boolean>(false);
  const [exportingFormat, setExportingFormat] = useState<"pdf" | "docx" | null>(null);
  const [forecastSummary, setForecastSummary] = useState<string | null>(null);

  // Base assumptions
  const baseCustomersRef = useRef<number>(500); // baseline customers per month
  const months = 12;

  // Pathway feed: update base customers from backend when connected
  useEffect(() => {
    if (!pathwayConnected) return;
    let mounted = true;
    let timer: any;

    const tick = async () => {
      try {
        const data = await getPathwayLive();
        if (!mounted) return;
        if (typeof data.customers === "number") {
          baseCustomersRef.current = clamp(Math.round(data.customers), 100, 10000);
        } else if (typeof data.revenueDeltaPct === "number") {
          const next = clamp(
            Math.round(baseCustomersRef.current * (1 + data.revenueDeltaPct)),
            100,
            10000
          );
          baseCustomersRef.current = next;
        }
      } catch (e) {
        toast.error("Failed to fetch live Pathway data");
      }
    };

    tick();
    timer = setInterval(tick, 10_000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [pathwayConnected]);

  // Scenario engine
  const forecast = useMemo(() => {
    const initialCustomers = baseCustomersRef.current;
    const custGrowthFromMarketing = clamp(marketing / 200_000, 0, 0.5); // up to +50%/yr due to marketing
    const monthlyGrowth = custGrowthFromMarketing / 12; // simple linearized monthly compounding

    let customers = initialCustomers;
    const data: Array<{
      month: string;
      revenue: number;
      expenses: number;
      profit: number;
      runway: number; // months remaining
      customers: number;
    }> = [];

    let cashBalance = cash;

    for (let i = 0; i < months; i++) {
      if (i > 0) customers = Math.round(customers * (1 + monthlyGrowth));

      const revenue = customers * price;
      const payroll = employees * salary;
      const ops = Math.round(0.15 * payroll); // basic ops overhead tied to team size
      const expenses = payroll + marketing + ops;
      const profit = revenue - expenses;
      cashBalance += profit;

      // estimated runway assuming current month repeating if negative cashflow; if profitable, set high
      const monthlyBurn = Math.max(expenses - revenue, 0);
      const runway = monthlyBurn > 0 ? cashBalance / monthlyBurn : 120; // cap at 10 years

      data.push({
        month: `M${i + 1}`,
        revenue,
        expenses,
        profit,
        runway,
        customers,
      });
    }

    return data;
  }, [employees, salary, marketing, price, cash]);

  const current = forecast[0];
  const last = forecast[forecast.length - 1];

  const exampleSummary = useMemo(() => {
    const hireText = `${employees} employee${employees === 1 ? "" : "s"} at ${currency(salary)}/month`;
    const startRunway = (() => {
      const burn = Math.max(current.expenses - current.revenue, 0);
      return burn > 0 ? cash / burn : Infinity;
    })();
    const endBurn = Math.max(last.expenses - last.revenue, 0);
    const endRunway = endBurn > 0 ? (cash + forecast.reduce((s, d) => s + d.profit, 0)) / endBurn : Infinity;

    const fmt = (n: number) => (n === Infinity ? "120+" : n.toFixed(1));

    return `If you hire ${hireText} and spend ${currency(marketing)} on marketing, runway changes from ${fmt(
      startRunway
    )} months → ${fmt(endRunway)} months.`;
  }, [employees, salary, marketing, current, last, cash, forecast]);

  // Bootstrap user and usage from backend
  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      try {
        setBootstrapping(true);
        let uid = localStorage.getItem("fh_user_id");
        if (!uid) {
          const user = await createUser("founder@example.com");
          uid = user.id;
          if (uid) localStorage.setItem("fh_user_id", uid);
        }
        if (cancelled) return;
        setUserId(uid);
        // fetch usage
        if (uid) await fetchUsage(uid);
      } catch (e: any) {
        toast.error(e?.message || "Failed to initialize user");
      } finally {
        if (!cancelled) setBootstrapping(false);
      }
    };
    init();
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchUsage = async (uid: string) => {
    try {
      const usage = await apiGetUsage(uid);
      setScenarioCount(Number(usage.scenarios_run || 0));
      setReportCount(Number(usage.reports_exported || 0));
    } catch (e: any) {
      toast.error(e?.message || "Failed to load usage counters");
    }
  };

  const onSimulate = async () => {
    if (!userId) return;
    try {
      setSimulating(true);
      const res = await simulateScenario({
        user_id: userId,
        employees,
        salary_per_employee: salary,
        marketing_spend: marketing,
        product_price: price,
      });
      setForecastSummary(res.scenario?.forecast_summary || null);
      setScenarioCount(res.usage?.scenarios_run ?? 0);
      setReportCount(res.usage?.reports_exported ?? 0);
      toast.success("Scenario simulated");
    } catch (e: any) {
      toast.error(e?.message || "Simulation failed (billing or compute error)");
    } finally {
      setSimulating(false);
    }
  };

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const onExport = async (format: "pdf" | "docx") => {
    if (!userId) return;
    try {
      setExportingFormat(format);
      const file = await exportReport({ user_id: userId, report_type: format });
      downloadBlob(file.blob, file.filename);
      if (userId) await fetchUsage(userId);
      toast.success(`Exported ${format.toUpperCase()}`);
    } catch (e: any) {
      toast.error(e?.message || "Report export failed (billing or generation error)");
    } finally {
      setExportingFormat(null);
    }
  };

  // UI helpers
  const SliderRow = ({
    label,
    value,
    onChange,
    min,
    max,
    step = 1,
    postfix = "",
  }: {
    label: string;
    value: number;
    onChange: (v: number) => void;
    min: number;
    max: number;
    step?: number;
    postfix?: string;
  }) => (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">{label}</Label>
        <span className="text-sm tabular-nums text-muted-foreground">
          {postfix === "₹"
            ? `${postfix}${value.toLocaleString("en-IN")}`
            : postfix === "/mo"
            ? `${value.toLocaleString()}${postfix}`
            : postfix === "₹/mo"
            ? `₹${value.toLocaleString("en-IN")}/mo`
            : value.toLocaleString("en-IN")}
        </span>
      </div>
      <Slider
        value={[value]}
        onValueChange={(v) => onChange(v[0])}
        min={min}
        max={max}
        step={step}
      />
    </div>
  );

  return (
    <div className="container mx-auto max-w-6xl py-8 space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Finance Helper (CFO Assistant)</h1>
          <p className="text-sm text-muted-foreground">Simulate pricing, hiring, and marketing to see revenue, expenses, and runway instantly.</p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="secondary">Scenarios: {scenarioCount}</Badge>
          <Badge variant="secondary">Reports: {reportCount}</Badge>
          <div className="flex items-center gap-2">
            <Label htmlFor="pathway">Live Pathway</Label>
            <Switch id="pathway" checked={pathwayConnected} onCheckedChange={setPathwayConnected} />
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="md:col-span-1">
          <CardHeader>
            <CardTitle>Inputs</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <SliderRow label="Employees" value={employees} onChange={setEmployees} min={0} max={50} />
            <SliderRow label="Salary (₹/mo)" value={salary} onChange={setSalary} min={10000} max={300000} step={1000} postfix="₹/mo" />
            <SliderRow label="Marketing (₹/mo)" value={marketing} onChange={setMarketing} min={0} max={500000} step={5000} postfix="₹/mo" />
            <SliderRow label="Price (₹)" value={price} onChange={setPrice} min={50} max={20000} step={10} postfix="₹" />
            <SliderRow label="Starting Cash (₹)" value={cash} onChange={setCash} min={100000} max={10_000_000} step={50_000} postfix="₹" />

            <div className="flex flex-wrap gap-2 pt-2">
              <Button onClick={onSimulate} disabled={bootstrapping || simulating}>
                {simulating && <span className="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent align-[-0.125em]"></span>}
                Simulate Scenario
              </Button>
              <Button variant="secondary" onClick={() => onExport("pdf")} disabled={bootstrapping || exportingFormat !== null}>
                {exportingFormat === "pdf" && <span className="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent align-[-0.125em]"></span>}
                Export PDF
              </Button>
              <Button variant="secondary" onClick={() => onExport("docx")} disabled={bootstrapping || exportingFormat !== null}>
                {exportingFormat === "docx" && <span className="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent align-[-0.125em]"></span>}
                Export DOCX
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">Base customers (live): {baseCustomersRef.current.toLocaleString()}</p>
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Forecast Overview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">Month 1</div>
                <div className="text-sm">Revenue: {currency(current.revenue)}</div>
                <div className="text-sm">Expenses: {currency(current.expenses)}</div>
                <div className="text-sm">Profit: {currency(current.profit)}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">Month 12</div>
                <div className="text-sm">Revenue: {currency(last.revenue)}</div>
                <div className="text-sm">Expenses: {currency(last.expenses)}</div>
                <div className="text-sm">Profit: {currency(last.profit)}</div>
              </div>
            </div>

            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={forecast} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" />
                  <YAxis tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
                  <Tooltip formatter={(v: number) => currency(v)} />
                  <Legend />
                  <Line type="monotone" dataKey="revenue" name="Revenue" stroke="var(--color-chart-2)" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="expenses" name="Expenses" stroke="var(--color-chart-1)" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="profit" name="Profit" stroke="var(--color-chart-4)" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={forecast} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <defs>
                    <linearGradient id="runwayGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--color-chart-3)" stopOpacity={0.8} />
                      <stop offset="95%" stopColor="var(--color-chart-3)" stopOpacity={0.1} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="month" />
                  <YAxis tickFormatter={(v) => `${v}m`} domain={[0, 120]} />
                  <Tooltip formatter={(v: number) => `${(v as number).toFixed(1)} months`} />
                  <Area type="monotone" dataKey="runway" name="Runway (months)" stroke="var(--color-chart-3)" fill="url(#runwayGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="rounded-md border p-3 text-sm">
              <p className="font-medium">Forecast Summary</p>
              <p className="text-muted-foreground">{forecastSummary ?? exampleSummary}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <footer className="text-xs text-muted-foreground text-center">
        Images/videos by Unsplash when used. This tool is for simulation purposes only; not financial advice.
      </footer>
    </div>
  );
}