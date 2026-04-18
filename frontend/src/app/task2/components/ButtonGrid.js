"use client";

import ErrorBanner from "@/components/ErrorBanner";
import LoadingSpinner from "@/components/LoadingSpinner";

export default function ButtonGrid({
  // Lists
  safeBrands,
  safeChannels,
  disableActions,
  dataReady,
  loading,
  err,
  // Year state
  availableYears,
  availableYearsBrandHealth,
  selectedYearsDrilldown,
  selectedYearsBrandHealth,
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
  getMonthlySalesByChannel,
  getMonthlySalesByBrand,
  getMonthlySalesByBrandChannel,
  getMonthlySalesByChannelBrand,
  getBrandItemProfitLoss,
  getBrandItemLocations,
  getBrandItemChannels,
  getLocationsSalesOnHandSummary,
  getProductSaleVsOnHand,
  getProductSaleVsOnHandLocations,
  handleClickBrandHealth,
  toggleYearBrandHealth,
  toggleYearDrilldown,
}) {
  const btnBase = "mt-3 ml-3 mr-3 mb-3 rounded-lg border border-slate-200 px-4 py-2 disabled:opacity-50 disabled:cursor-not-allowed";

  return (
    <div className="mb-4 rounded-2xl border border-slate-200 p-4">
      {/* Monthly / Weekly Sales by Channel & Brand */}
      <button onClick={() => getMonthlySalesByChannel("monthly")} disabled={disableActions} className={`${btnBase} bg-green-100 hover:bg-green-200`}>
        Monthly Sales Data by Channel
      </button>
      <button onClick={() => getMonthlySalesByBrand("monthly")} disabled={disableActions} className={`${btnBase} bg-green-100 hover:bg-green-200`}>
        Monthly Sales Data by Brand
      </button>
      <br />
      <button onClick={() => getMonthlySalesByChannel("weekly")} disabled={disableActions} className={`${btnBase} bg-orange-100 hover:bg-green-200`}>
        Weekly Sales Data by Channel
      </button>
      <button onClick={() => getMonthlySalesByBrand("weekly")} disabled={disableActions} className={`${btnBase} bg-orange-100 hover:bg-green-200`}>
        Weekly Sales Data by Brand
      </button>
      <br />

      {/* Brand Health Summary */}
      <div className="inline-flex items-center gap-4 p-4 rounded-lg border border-slate-200 px-4 py-2 bg-pink-100 hover:bg-pink-200">
        <button onClick={handleClickBrandHealth} disabled={disableActions} className="rounded-lg border border-slate-200 px-4 py-2 bg-pink-100 hover:bg-pink-200 disabled:opacity-50 disabled:cursor-not-allowed">
          Brand Health Summary
          {selectedYearsBrandHealth.length > 0 && ` (${selectedYearsBrandHealth.join(", ")})`}
        </button>
        <div className="flex gap-2">
          {availableYearsBrandHealth.map((year) => (
            <button
              key={year}
              type="button"
              onClick={() => toggleYearBrandHealth(year)}
              disabled={disableActions}
              className={`px-3 py-1 rounded-md text-sm border transition disabled:opacity-50 ${
                selectedYearsBrandHealth.includes(year)
                  ? "bg-pink-500 text-white"
                  : "bg-white hover:bg-gray-200"
              }`}
            >
              {year}
            </button>
          ))}
        </div>
      </div>

      {/* Locations Summary */}
      <button onClick={() => getLocationsSalesOnHandSummary()} disabled={disableActions} className={`${btnBase} bg-green-100 hover:bg-green-200`}>
        Locations Sales / OnHand Summary
      </button>
      <br />

      {/* Brand Channel Summary */}
      <DrilldownBar
        label="Brand Channel Summary"
        bgLabel="bg-blue-100" bgSelect="bg-blue-200" bgGo="bg-blue-100 hover:bg-blue-200"
        bgYearPanel="bg-blue-50" activeYearClass="bg-blue-600 text-white border-blue-600"
        years={availableYears.slice(0, 3)}
        selectedYears={selectedYearsDrilldown}
        toggleYear={toggleYearDrilldown}
        items={safeBrands}
        selectedItem={selectedBrand1}
        setSelectedItem={setSelectedBrand1}
        placeholder="Select Brand"
        onGo={() => getMonthlySalesByBrandChannel("monthly")}
        disabled={disableActions}
        goDisabled={!selectedBrand1 || disableActions}
        keyPrefix="bc"
      />

      {/* Channel Brand Summary */}
      <DrilldownBar
        label="Channel Brand Summary"
        bgLabel="bg-yellow-100" bgSelect="bg-yellow-200" bgGo="bg-yellow-100 hover:bg-yellow-200"
        bgYearPanel="bg-yellow-50" activeYearClass="bg-yellow-600 text-white border-yellow-600"
        years={availableYears.slice(0, 3)}
        selectedYears={selectedYearsDrilldown}
        toggleYear={toggleYearDrilldown}
        items={safeChannels}
        selectedItem={selectedChannel1}
        setSelectedItem={setSelectedChannel1}
        placeholder="Select Channel"
        onGo={() => getMonthlySalesByChannelBrand("monthly")}
        disabled={disableActions}
        goDisabled={!selectedChannel1 || disableActions}
        keyPrefix="cb"
      />
      <br />

      {/* Brand Item Profit Loss */}
      <BrandSelectBar
        label="Brand Item Profit Loss Summary"
        brands={safeBrands}
        selected={selectedBrand2}
        setSelected={setSelectedBrand2}
        onGo={() => getBrandItemProfitLoss()}
        disabled={disableActions}
        goDisabled={!selectedBrand2 || disableActions}
      />

      {/* Brand Item Locations */}
      <BrandOutputBar
        label="Brand Item Locations"
        brands={safeBrands}
        selected={selectedBrand3}
        setSelected={setSelectedBrand3}
        outputMode={outputMode3}
        setOutputMode={setOutputMode3}
        onGo={() => getBrandItemLocations(selectedBrand3, outputMode3)}
        disabled={disableActions}
        goDisabled={!selectedBrand3 || disableActions}
      />

      {/* Brand Item Channels */}
      <BrandOutputBar
        label="Brand Item Channels"
        brands={safeBrands}
        selected={selectedBrand4}
        setSelected={setSelectedBrand4}
        outputMode={outputMode4}
        setOutputMode={setOutputMode4}
        onGo={() => getBrandItemChannels(selectedBrand4, outputMode4)}
        disabled={disableActions}
        goDisabled={!selectedBrand4 || disableActions}
      />
      <br />

      {/* Product Sale Vs. OnHand */}
      <DrilldownBar
        label="Product Sale Vs. OnHand"
        bgLabel="bg-teal-100" bgSelect="bg-teal-200" bgGo="bg-teal-100 hover:bg-teal-200"
        bgYearPanel="bg-teal-50" activeYearClass="bg-teal-600 text-white border-teal-600"
        years={availableYears.slice(0, 3)}
        selectedYears={selectedYearsDrilldown}
        toggleYear={toggleYearDrilldown}
        items={safeBrands}
        selectedItem={selectedBrandPSO}
        setSelectedItem={setSelectedBrandPSO}
        placeholder="Select Brand"
        onGo={() => getProductSaleVsOnHand()}
        disabled={disableActions}
        goDisabled={!selectedBrandPSO || disableActions}
        keyPrefix="pso"
      />

      {/* Product Sale Vs. OnHand by Locations */}
      <DrilldownBar
        label="Product Sale Vs. OnHand by Locations"
        bgLabel="bg-emerald-100" bgSelect="bg-emerald-200" bgGo="bg-emerald-100 hover:bg-emerald-200"
        bgYearPanel="bg-emerald-50" activeYearClass="bg-emerald-600 text-white border-emerald-600"
        years={availableYears.slice(0, 3)}
        selectedYears={selectedYearsDrilldown}
        toggleYear={toggleYearDrilldown}
        items={safeBrands}
        selectedItem={selectedBrandPSOL}
        setSelectedItem={setSelectedBrandPSOL}
        placeholder="Select Brand"
        onGo={() => getProductSaleVsOnHandLocations()}
        disabled={disableActions}
        goDisabled={!selectedBrandPSOL || disableActions}
        keyPrefix="psol"
      />

      {loading && <LoadingSpinner message="Fetching data\u2026" />}
      <ErrorBanner message={err} />
    </div>
  );
}

/**
 * Reusable drilldown bar: label + year toggles + select + GO button.
 */
function DrilldownBar({
  label, bgLabel, bgSelect, bgGo, bgYearPanel, activeYearClass,
  years, selectedYears, toggleYear,
  items, selectedItem, setSelectedItem, placeholder,
  onGo, disabled, goDisabled, keyPrefix,
}) {
  return (
    <div className="mt-3 ml-3 mr-3 mb-3 inline-flex rounded-lg border border-slate-200 overflow-hidden">
      <p className={`px-4 py-2 ${bgLabel} font-semibold`}>{label}</p>
      <div className={`px-3 py-2 ${bgYearPanel} border-r border-slate-200 flex items-center gap-2`}>
        <span className="text-xs font-medium">Years</span>
        {years.map((y) => (
          <button
            key={`${keyPrefix}-${y}`}
            type="button"
            onClick={() => toggleYear(y)}
            disabled={disabled}
            className={`px-2 py-1 rounded-md text-xs border disabled:opacity-50 ${
              selectedYears.includes(y)
                ? `${activeYearClass}`
                : "bg-white hover:bg-gray-100 border-slate-200"
            }`}
          >
            {y}
          </button>
        ))}
      </div>
      <select
        value={selectedItem}
        onChange={(e) => setSelectedItem(e.target.value)}
        className={`px-4 py-2 ${bgSelect} border-r border-slate-200 outline-none cursor-pointer`}
        disabled={!items.length || disabled}
      >
        <option value="">{items.length ? placeholder : "Loading..."}</option>
        {items.map((item, i) => (
          <option key={item ?? i} value={item ?? ""}>{item ?? "(unknown)"}</option>
        ))}
      </select>
      <button
        onClick={onGo}
        disabled={goDisabled}
        className={`px-4 py-2 ${bgGo} disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        GO
      </button>
    </div>
  );
}

/**
 * Simple brand select + GO bar (no year toggles).
 */
function BrandSelectBar({ label, brands, selected, setSelected, onGo, disabled, goDisabled }) {
  return (
    <div className="mt-3 ml-3 mr-3 mb-3 inline-flex rounded-lg border border-slate-200 overflow-hidden">
      <p className="px-4 py-2 bg-blue-100 font-semibold">{label}</p>
      <select
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        className="px-4 py-2 bg-blue-200 border-r border-slate-200 outline-none cursor-pointer"
        disabled={!brands.length || disabled}
      >
        <option value="">{brands.length ? "Select Brand" : "Loading brands..."}</option>
        {brands.map((brand, i) => (
          <option key={brand ?? i} value={brand ?? ""}>{brand ?? "(unknown)"}</option>
        ))}
      </select>
      <button onClick={onGo} disabled={goDisabled} className="px-4 py-2 bg-blue-100 hover:bg-blue-200 disabled:opacity-50 disabled:cursor-not-allowed">
        GO
      </button>
    </div>
  );
}

/**
 * Brand select + output mode select + GO bar.
 */
function BrandOutputBar({ label, brands, selected, setSelected, outputMode, setOutputMode, onGo, disabled, goDisabled }) {
  return (
    <div className="mt-3 ml-3 mr-3 mb-3 inline-flex rounded-lg border border-slate-200 overflow-hidden">
      <p className="px-4 py-2 bg-blue-100 font-semibold">{label}</p>
      <select
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        className="px-4 py-2 bg-blue-200 border-r border-slate-200 outline-none cursor-pointer"
        disabled={!brands.length || disabled}
      >
        <option value="">{brands.length ? "Select Brand" : "Loading brands..."}</option>
        {brands.map((brand, i) => (
          <option key={brand ?? i} value={brand ?? ""}>{brand ?? "(unknown)"}</option>
        ))}
      </select>
      <select
        value={outputMode}
        onChange={(e) => setOutputMode(e.target.value)}
        className="px-4 py-2 bg-blue-200 border-r border-slate-200 outline-none cursor-pointer"
        disabled={!brands.length || disabled}
      >
        <option value="">Select Output</option>
        <option value="item">Item</option>
        <option value="location">Location</option>
      </select>
      <button onClick={onGo} disabled={goDisabled} className="px-4 py-2 bg-blue-100 hover:bg-blue-200 disabled:opacity-50 disabled:cursor-not-allowed">
        GO
      </button>
    </div>
  );
}
