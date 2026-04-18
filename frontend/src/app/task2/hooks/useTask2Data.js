"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import api, { isAbortError } from "@/utils/api";
import { buildColorMap } from "@/utils/chartColors";

/**
 * Parses the standard {columns, index, data} payload from backend matrix endpoints.
 */
function parseMatrixPayload(response) {
  const payload = typeof response.data === "string" ? JSON.parse(response.data) : response.data;
  const { columns, index, data } = payload || {};
  if (!Array.isArray(columns) || !Array.isArray(data)) throw new Error("Invalid payload");
  return data.map((row, r) => {
    const obj = Object.fromEntries(row.map((v, i) => [columns[i], v]));
    return { __index: Array.isArray(index) ? index[r] : r, ...obj };
  });
}

/**
 * Normalizes an API response into a flat array regardless of backend shape.
 */
function parseListPayload(response) {
  const raw = typeof response.data === "string" ? JSON.parse(response.data) : response.data;
  if (Array.isArray(raw)) return raw;
  if (Array.isArray(raw?.brands)) return raw.brands;
  if (Array.isArray(raw?.brandList)) return raw.brandList;
  if (Array.isArray(raw?.data)) return raw.data;
  if (Array.isArray(raw?.list)) return raw.list;
  return [];
}

export default function useTask2Data() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [tableColFilterOn, setTableColFilterOn] = useState(true);
  const [viewMode, setViewMode] = useState("");

  const [selectedBrand1, setSelectedBrand1] = useState("");
  const [selectedBrand2, setSelectedBrand2] = useState("");
  const [selectedBrand3, setSelectedBrand3] = useState("");
  const [selectedBrand4, setSelectedBrand4] = useState("");
  const [outputMode3, setOutputMode3] = useState("Item");
  const [outputMode4, setOutputMode4] = useState("Item");

  const [brandList, setBrandList] = useState([]);
  const [channelList, setChannelList] = useState([]);
  const [selectedChannel1, setSelectedChannel1] = useState("");

  const [fileDate, setFileDate] = useState("");
  const [dataReady, setDataReady] = useState(false);

  const currentYear = new Date().getFullYear();
  const availableYears = [currentYear, currentYear - 1, currentYear - 2, currentYear - 3];
  const availableYearsBrandHealth = [currentYear, currentYear - 1, currentYear - 2];

  const [selectedYearsDrilldown, setSelectedYearsDrilldown] = useState([currentYear]);
  const [selectedYearsBrandHealth, setSelectedYearsBrandHealth] = useState([]);

  const [selectedBrandPSO, setSelectedBrandPSO] = useState("");
  const [selectedBrandPSOL, setSelectedBrandPSOL] = useState("");

  const safeBrands = Array.isArray(brandList) ? brandList : [];
  const safeChannels = Array.isArray(channelList) ? channelList : [];
  const disableActions = !dataReady || loading;

  const channelColorMap = useMemo(() => buildColorMap(safeChannels), [safeChannels]);
  const brandColorMap = useMemo(() => buildColorMap(safeBrands), [safeBrands]);

  // --- Fetch helpers ---

  const fetchMatrix = useCallback(async (url, mode, colFilter) => {
    try {
      setLoading(true);
      setErr(null);
      setViewMode(mode);
      const response = await api.get(url, { responseType: "json" });
      setRows(parseMatrixPayload(response));
      setTableColFilterOn(colFilter);
    } catch (e) {
      setErr(e?.message || "Failed to fetch data");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchMatrixPost = useCallback(async (url, body, mode, colFilter) => {
    try {
      setLoading(true);
      setErr(null);
      setViewMode(mode);
      const response = await api.post(url, body, { responseType: "json" });
      setRows(parseMatrixPayload(response));
      setTableColFilterOn(colFilter);
    } catch (e) {
      setErr(e?.message || "Failed to fetch data");
    } finally {
      setLoading(false);
    }
  }, []);

  // --- View-specific fetch functions ---

  const getProductSaleVsOnHand = useCallback(() => {
    const yearParams = selectedYearsDrilldown.map((y) => `year_list=${y}`).join("&");
    fetchMatrix(
      `/api/product_sale_vs_onhand?brand_name=${encodeURIComponent(selectedBrandPSO)}&time_frame=monthly${yearParams ? "&" + yearParams : ""}`,
      "product_sale_onhand", false
    );
  }, [fetchMatrix, selectedBrandPSO, selectedYearsDrilldown]);

  const getProductSaleVsOnHandLocations = useCallback(() => {
    const yearParams = selectedYearsDrilldown.map((y) => `year_list=${y}`).join("&");
    fetchMatrix(
      `/api/product_sale_vs_onhand_locations?brand_name=${encodeURIComponent(selectedBrandPSOL)}&time_frame=monthly${yearParams ? "&" + yearParams : ""}`,
      "product_sale_onhand_locations", false
    );
  }, [fetchMatrix, selectedBrandPSOL, selectedYearsDrilldown]);

  const getMonthlySalesByChannel = useCallback((timeFrame = "monthly") => {
    fetchMatrix(
      `/api/sale_record_by_channel?time_frame=${encodeURIComponent(timeFrame)}`,
      "sales_channel", true
    );
  }, [fetchMatrix]);

  const getMonthlySalesByBrand = useCallback((timeFrame = "monthly") => {
    fetchMatrix(
      `/api/sale_record_by_brand?time_frame=${encodeURIComponent(timeFrame)}`,
      "sales_brand", true
    );
  }, [fetchMatrix]);

  const getMonthlySalesByBrandChannel = useCallback((timeFrame = "monthly") => {
    const yearsQs = selectedYearsDrilldown.map((y) => `year_list=${encodeURIComponent(String(y))}`).join("&");
    fetchMatrix(
      `/api/sale_brand_channel?time_frame=${encodeURIComponent(timeFrame)}&brand_name=${encodeURIComponent(selectedBrand1 || "")}&file_date=${encodeURIComponent(fileDate || "")}${yearsQs ? `&${yearsQs}` : ""}`,
      "brand_channel", true
    );
  }, [fetchMatrix, selectedBrand1, fileDate, selectedYearsDrilldown]);

  const getMonthlySalesByChannelBrand = useCallback((timeFrame = "monthly") => {
    const yearsQs = selectedYearsDrilldown.map((y) => `year_list=${encodeURIComponent(String(y))}`).join("&");
    fetchMatrix(
      `/api/sale_channel_brand?time_frame=${encodeURIComponent(timeFrame)}&channel_name=${encodeURIComponent(selectedChannel1 || "")}&file_date=${encodeURIComponent(fileDate || "")}${yearsQs ? `&${yearsQs}` : ""}`,
      "channel_brand", false
    );
  }, [fetchMatrix, selectedChannel1, fileDate, selectedYearsDrilldown]);

  const getBrandHealthSummary = useCallback((years) => {
    fetchMatrixPost(`/api/brand_health_summary`, { year_list: years }, "brand_health", false);
  }, [fetchMatrixPost]);

  const getLocationsSalesOnHandSummary = useCallback(() => {
    fetchMatrix(`/api/locations_sale_onhand_summary`, "locations", false);
  }, [fetchMatrix]);

  const getBrandItemProfitLoss = useCallback(() => {
    fetchMatrix(
      `/api/sale_brand_profit_loss?brand_name=${encodeURIComponent(selectedBrand2 || "")}`,
      "profit_loss", false
    );
  }, [fetchMatrix, selectedBrand2]);

  const getBrandItemLocations = useCallback((brand_name, output_mode) => {
    fetchMatrix(
      `/api/sale_brand_item_locations?brand_name=${encodeURIComponent(brand_name || "")}&output=${output_mode}`,
      "item_locations", false
    );
  }, [fetchMatrix]);

  const getBrandItemChannels = useCallback((brand_name, output_mode) => {
    fetchMatrix(
      `/api/sale_brand_item_channels?brand_name=${encodeURIComponent(brand_name || "")}&output=${output_mode}`,
      "item_channels", false
    );
  }, [fetchMatrix]);

  // --- Toggle helpers ---

  const toggleYearBrandHealth = (year) => {
    setSelectedYearsBrandHealth((prev) =>
      prev.includes(year) ? prev.filter((y) => y !== year) : [...prev, year]
    );
  };

  const handleClickBrandHealth = () => {
    if (selectedYearsBrandHealth.length === 0) {
      alert("Please select at least one year");
      return;
    }
    getBrandHealthSummary(selectedYearsBrandHealth);
  };

  const toggleYearDrilldown = (year) => {
    setSelectedYearsDrilldown((prev) =>
      prev.includes(year) ? prev.filter((y) => y !== year) : [...prev, year]
    );
  };

  // --- Init ---

  useEffect(() => {
    const controller = new AbortController();
    const s = controller.signal;

    const init = async () => {
      try {
        const res = await api.get("/api/data_status", { responseType: "json", signal: s });
        setDataReady(res.data?.state === "ready");
      } catch (e) {
        if (!isAbortError(e)) setDataReady(false);
      }

      try {
        setLoading(true);
        const [brandRes, channelRes, dateRes] = await Promise.all([
          api.get("/api/get_brand_list", { responseType: "json", signal: s }),
          api.get("/api/get_channel_list", { responseType: "json", signal: s }),
          api.get("/api/get_file_date", { responseType: "json", signal: s }),
        ]);
        setBrandList(parseListPayload(brandRes));
        setChannelList(parseListPayload(channelRes));
        const extracted = (typeof dateRes.data === "string" ? JSON.parse(dateRes.data) : dateRes.data)?.extracted_date;
        setFileDate(typeof extracted === "string" ? extracted : "");
      } catch (e) {
        if (!isAbortError(e)) {
          setErr(e?.message || "Failed to initialize");
          setBrandList([]);
          setChannelList([]);
        }
      } finally {
        setLoading(false);
      }
    };

    init();
    return () => controller.abort();
  }, []);

  return {
    // Data
    rows, loading, err, tableColFilterOn, viewMode,
    // Lists
    safeBrands, safeChannels, disableActions,
    // Color maps
    channelColorMap, brandColorMap,
    // Year state
    currentYear, availableYears, availableYearsBrandHealth,
    selectedYearsDrilldown, selectedYearsBrandHealth,
    dataReady,
    // Brand/channel selections
    selectedBrand1, setSelectedBrand1,
    selectedBrand2, setSelectedBrand2,
    selectedBrand3, setSelectedBrand3,
    selectedBrand4, setSelectedBrand4,
    outputMode3, setOutputMode3,
    outputMode4, setOutputMode4,
    selectedChannel1, setSelectedChannel1,
    selectedBrandPSO, setSelectedBrandPSO,
    selectedBrandPSOL, setSelectedBrandPSOL,
    // Actions
    getMonthlySalesByChannel, getMonthlySalesByBrand,
    getMonthlySalesByBrandChannel, getMonthlySalesByChannelBrand,
    getBrandItemProfitLoss, getBrandItemLocations, getBrandItemChannels,
    getLocationsSalesOnHandSummary,
    getProductSaleVsOnHand, getProductSaleVsOnHandLocations,
    handleClickBrandHealth,
    toggleYearBrandHealth, toggleYearDrilldown,
  };
}
