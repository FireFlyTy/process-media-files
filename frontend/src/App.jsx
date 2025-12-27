import React, { useState, useCallback, useEffect } from 'react';
import { Upload, FileText, Image, AlertCircle, CheckCircle, Clock, Trash2, RefreshCw, FileCheck, Shield, Camera, Building, User, Calendar, MapPin, Hash, RotateCcw, XCircle, Download, Eye, X, FileDown } from 'lucide-react';
import axios from 'axios';

const API_URL = 'http://localhost:8000';

// Human-readable document type labels
const DOCUMENT_TYPE_LABELS = {
  damage_act: 'Act of Damage',
  official_certificate: 'Official Certificate',
  photo_collection: 'Photo Collection',
  identity_document: 'Identity Document',
  property_document: 'Property Document',
  utility_bill: 'Utility Bill',
  court_decision: 'Court Decision',
  registration_extract: 'Registry Extract',
  medical_record: 'Medical Record',
  financial_statement: 'Financial Statement',
  application_form: 'Application Form',
  damage_photo: 'Damage Photo',
  property_exterior: 'Property Exterior',
  property_interior: 'Property Interior',
  document_photo: 'Document Photo',
  identity_photo: 'Identity Photo',
  before_after: 'Before/After Photo',
  screenshot: 'Screenshot',
  other: 'Other',
};

const formatDocumentType = (type) => DOCUMENT_TYPE_LABELS[type] || type;

// Decision badge component
const DecisionBadge = ({ decision, confidence }) => {
  const styles = {
    ACCEPT: 'bg-emerald-100 text-emerald-800 border-emerald-300',
    REVIEW: 'bg-amber-100 text-amber-800 border-amber-300',
    REJECT: 'bg-red-100 text-red-800 border-red-300',
  };

  const icons = {
    ACCEPT: <CheckCircle size={16} />,
    REVIEW: <Clock size={16} />,
    REJECT: <AlertCircle size={16} />,
  };

  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border font-bold text-sm ${styles[decision] || styles.REJECT}`}>
      {icons[decision]}
      {decision}
      <span className="text-xs font-normal opacity-70">
        {Math.round(confidence * 100)}%
      </span>
    </div>
  );
};

// File item in list
const FileItem = ({ file, isSelected, onClick, onDelete, onRetry, onView }) => {
  const statusIcons = {
    pending: <Clock size={16} className="text-slate-400 animate-pulse" />,
    processing: <RefreshCw size={16} className="text-blue-500 animate-spin" />,
    completed: file.result?.decision === 'ACCEPT' 
      ? <CheckCircle size={16} className="text-emerald-500" />
      : file.result?.decision === 'REVIEW'
        ? <Clock size={16} className="text-amber-500" />
        : <AlertCircle size={16} className="text-red-500" />,
    error: <AlertCircle size={16} className="text-red-500" />,
  };

  const isImage = file.type?.startsWith('image/');
  const canRetry = file.status === 'error' || file.status === 'completed';
  const canView = file.taskId && (file.status === 'completed' || file.status === 'error');
  const progress = file.progress || 0;

  return (
    <div className="group flex items-center gap-1">
      {/* Main card */}
      <div
        onClick={onClick}
        className={`relative overflow-hidden rounded-xl cursor-pointer transition-all border-2 flex-1 ${
          isSelected 
            ? 'bg-teal-50 border-teal-400' 
            : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50'
        }`}
      >
        {/* Progress bar background */}
        {file.status === 'processing' && (
          <div 
            className="absolute inset-0 bg-blue-50 transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        )}
        
        {/* Content */}
        <div className="relative flex items-center gap-3 p-3">
          <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
            {isImage ? <Image size={20} className="text-slate-500" /> : <FileText size={20} className="text-slate-500" />}
          </div>
          
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 truncate">{file.name}</p>
            <p className="text-xs text-slate-500 truncate">
              {file.status === 'processing' 
                ? `${progress}% — ${file.stage || 'Processing...'}`
                : file.status}
              {file.retryCount > 0 && ` (retry #${file.retryCount})`}
            </p>
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0">
            {statusIcons[file.status]}
            {canView && (
              <button
                onClick={(e) => { e.stopPropagation(); onView(file); }}
                className="p-1.5 rounded-lg text-slate-400 hover:text-teal-500 hover:bg-teal-50 transition-colors"
                title="View document"
              >
                <Eye size={14} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Hover actions - outside the card */}
      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
        {canRetry && (
          <button
            onClick={(e) => { e.stopPropagation(); onRetry(file.id); }}
            className="p-1.5 rounded-lg text-slate-300 hover:text-blue-500 hover:bg-blue-50 transition-colors"
            title="Retry"
          >
            <RotateCcw size={14} />
          </button>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(file.id); }}
          className="p-1.5 rounded-lg text-slate-300 hover:text-red-500 hover:bg-red-50 transition-colors"
          title="Delete"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
};

// Analysis section (from LLM classification + extraction)
const AnalysisSection = ({ analysis }) => {
  if (!analysis) return null;

  const fileType = analysis.file_type;
  const isPDF = fileType === 'pdf';

  // Check for specific warnings
  const warnings = analysis.warnings || [];
  const extractedData = analysis.extracted_data || {};
  
  // Determine if stamp has a warning (government stamp on non-official doc)
  const hasGovernmentStampWarning = warnings.some(w => 
    w.toLowerCase().includes('government stamp')
  );
  
  // Determine badge style based on element presence and context
  const isOfficialDoc = ['official_certificate', 'court_decision', 'registration_extract'].includes(analysis.document_type);
  
  const getStampBadgeStyle = () => {
    if (analysis.has_stamp) {
      // Has stamp - but check if it's unexpected (warning)
      if (hasGovernmentStampWarning) {
        return 'bg-amber-50 text-amber-600 border border-amber-200'; // Unexpected stamp
      }
      return 'bg-emerald-50 text-emerald-700 border border-emerald-200'; // Expected stamp
    }
    // No stamp
    if (isOfficialDoc) {
      return 'bg-amber-50 text-amber-600 border border-amber-200'; // Missing required stamp
    }
    return 'bg-slate-50 text-slate-400 border border-slate-200'; // OK, not required
  };
  
  const getBadgeStyle = (hasElement) => {
    if (hasElement) return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
    if (isOfficialDoc) return 'bg-amber-50 text-amber-600 border border-amber-200';
    return 'bg-slate-50 text-slate-400 border border-slate-200';
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-4 flex items-center gap-2">
        <FileCheck size={14} className="text-teal-600" />
        Document Analysis
      </h3>

      <div className="space-y-3">
        {/* Document type */}
        <div className="flex justify-between items-start">
          <span className="text-sm text-slate-600">Document Type</span>
          <div className="text-right">
            <span className="text-sm font-bold text-slate-800 block">{formatDocumentType(analysis.document_type)}</span>
            <span className="text-xs text-slate-500">{analysis.document_type_ua}</span>
          </div>
        </div>

        {isPDF && (
          <>
            <div className="flex justify-between">
              <span className="text-sm text-slate-600">Creation Method</span>
              <span className="text-sm text-slate-800 capitalize">{analysis.creation_method?.replace('_', ' ')}</span>
            </div>
            
            {analysis.document_date && (
              <div className="flex justify-between">
                <span className="text-sm text-slate-600 flex items-center gap-1">
                  <Calendar size={12} />
                  Document Date
                </span>
                <span className="text-sm text-slate-800">{analysis.document_date}</span>
              </div>
            )}

            {analysis.issuing_authority && (
              <div className="mt-2">
                <span className="text-xs text-slate-500 flex items-center gap-1 mb-1">
                  <Building size={12} />
                  Issuing Authority
                </span>
                <p className="text-sm text-slate-800 bg-slate-50 p-2 rounded">{analysis.issuing_authority}</p>
              </div>
            )}

            {/* Official elements grid */}
            <div className="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-slate-100">
              <div className={`text-center p-2 rounded-lg ${getStampBadgeStyle()}`}>
                <span className="text-xs font-bold">Stamp</span>
                <p className="text-lg">{analysis.has_stamp ? '✓' : '—'}</p>
                {hasGovernmentStampWarning && <p className="text-[10px]">gov</p>}
              </div>
              <div className={`text-center p-2 rounded-lg ${getBadgeStyle(analysis.has_signature)}`}>
                <span className="text-xs font-bold">Signature</span>
                <p className="text-lg">{analysis.has_signature ? '✓' : '—'}</p>
              </div>
              <div className={`text-center p-2 rounded-lg ${getBadgeStyle(analysis.has_letterhead)}`}>
                <span className="text-xs font-bold">Letterhead</span>
                <p className="text-lg">{analysis.has_letterhead ? '✓' : '—'}</p>
              </div>
            </div>

            {/* Images in document */}
            {analysis.has_images && (
              <div className="mt-3 pt-3 border-t border-slate-100">
                <p className="text-xs font-bold text-slate-500 mb-2 flex items-center gap-1">
                  <Camera size={12} />
                  Photos in Document ({analysis.images_count})
                </p>
                <div className={`p-2 rounded-lg ${analysis.images_match_claims === false ? 'bg-red-50 border border-red-200' : 'bg-slate-50'}`}>
                  {analysis.images_match_claims === false && (
                    <p className="text-xs font-bold text-red-600 mb-1">⚠️ Images don't match claims!</p>
                  )}
                  <ul className="text-xs text-slate-600 space-y-1">
                    {analysis.images_description?.map((desc, i) => (
                      <li key={i}>• {desc}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </>
        )}

        {/* Image-specific fields */}
        {!isPDF && (
          <>
            {analysis.shows_damage !== undefined && (
              <div className="flex justify-between">
                <span className="text-sm text-slate-600">Shows Damage</span>
                <span className={`text-sm font-bold ${analysis.shows_damage ? 'text-emerald-600' : 'text-slate-400'}`}>
                  {analysis.shows_damage ? 'Yes' : 'No'}
                </span>
              </div>
            )}
            {analysis.damage_severity && (
              <div className="flex justify-between">
                <span className="text-sm text-slate-600">Damage Severity</span>
                <span className="text-sm font-mono text-slate-800">{analysis.damage_severity}</span>
              </div>
            )}
          </>
        )}
        
        {/* Brief description */}
        {analysis.brief_description && (
          <div className="mt-3 pt-3 border-t border-slate-100">
            <p className="text-xs font-bold text-slate-500 mb-1">Description</p>
            <p className="text-sm text-slate-700">{analysis.brief_description}</p>
          </div>
        )}

        {/* Content summary */}
        {analysis.content_summary && (
          <div className="mt-3 pt-3 border-t border-slate-100">
            <p className="text-xs font-bold text-slate-500 mb-1">Content Summary</p>
            <p className="text-sm text-slate-700">{analysis.content_summary}</p>
          </div>
        )}
      </div>
    </div>
  );
};

// Extracted data section (type-specific)
const ExtractedDataSection = ({ extractedData, documentType, warnings = [] }) => {
  if (!extractedData || Object.keys(extractedData).length === 0) return null;

  // Check if there are editing-related warnings
  const hasEditingWarning = warnings.some(w => 
    w.toLowerCase().includes('photoshop') || 
    w.toLowerCase().includes('editing software') ||
    w.toLowerCase().includes('edited') ||
    w.toLowerCase().includes('manipulation')
  );

  // Field labels for better display
  const fieldLabels = {
    document_number: { label: 'Document Number', icon: Hash },
    letterhead_authority: { label: 'Letterhead', icon: Building },
    stamp_authority: { label: 'Stamp Authority', icon: Shield },
    signatures_count: { label: 'Signatures Count', icon: User },
    signatures_details: { label: 'Signatures', icon: User },
    property_address: { label: 'Property Address', icon: MapPin },
    owner_name: { label: 'Owner Name', icon: User },
    damage_description: { label: 'Damage Description', icon: AlertCircle },
    damage_date: { label: 'Damage Date', icon: Calendar },
    act_date: { label: 'Act Date', icon: Calendar },
    witnesses_count: { label: 'Witnesses', icon: User },
    witnesses_names: { label: 'Witness Names', icon: User },
    holder_name: { label: 'Holder Name', icon: User },
    appears_authentic: { label: 'Appears Authentic', icon: Shield },
  };

  // Helper to render a value safely
  const renderValue = (value) => {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? '✓ Yes' : '— No';
    if (typeof value === 'string' || typeof value === 'number') return String(value);
    if (Array.isArray(value)) return value.join(', ');
    if (typeof value === 'object') {
      // Render object as key-value pairs
      return Object.entries(value)
        .filter(([k, v]) => v !== null && v !== undefined)
        .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${renderValue(v)}`)
        .join('; ');
    }
    return String(value);
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-4 flex items-center gap-2">
        <FileText size={14} className="text-teal-600" />
        Extracted Data
      </h3>

      <div className="space-y-3">
        {Object.entries(extractedData).map(([key, value]) => {
          if (value === null || value === undefined) return null;
          
          const config = fieldLabels[key] || { label: key.replace(/_/g, ' '), icon: null };
          const Icon = config.icon;

          // Special handling for appears_authentic with editing warnings
          if (key === 'appears_authentic') {
            const isCompromised = hasEditingWarning;
            const displayValue = isCompromised ? '⚠️ Questionable' : (value ? '✓ Yes' : '✗ No');
            const colorClass = isCompromised 
              ? 'text-amber-600 bg-amber-50' 
              : (value ? 'text-emerald-600' : 'text-red-600');
            
            return (
              <div key={key} className={`flex justify-between items-center p-2 rounded ${isCompromised ? 'bg-amber-50' : ''}`}>
                <span className="text-sm text-slate-600 flex items-center gap-1">
                  {Icon && <Icon size={12} />}
                  {config.label}
                </span>
                <span className={`text-sm font-bold ${colorClass}`}>
                  {displayValue}
                </span>
              </div>
            );
          }

          // Handle arrays
          if (Array.isArray(value)) {
            return (
              <div key={key} className="mt-2">
                <span className="text-xs text-slate-500 flex items-center gap-1 mb-1">
                  {Icon && <Icon size={12} />}
                  {config.label}
                </span>
                <ul className="text-sm text-slate-700 bg-slate-50 p-2 rounded space-y-1">
                  {value.map((item, i) => (
                    <li key={i}>• {renderValue(item)}</li>
                  ))}
                </ul>
              </div>
            );
          }

          // Handle booleans
          if (typeof value === 'boolean') {
            return (
              <div key={key} className="flex justify-between">
                <span className="text-sm text-slate-600 flex items-center gap-1">
                  {Icon && <Icon size={12} />}
                  {config.label}
                </span>
                <span className={`text-sm font-bold ${value ? 'text-emerald-600' : 'text-slate-400'}`}>
                  {value ? '✓ Yes' : '— No'}
                </span>
              </div>
            );
          }

          // Handle objects (nested data)
          if (typeof value === 'object') {
            return (
              <div key={key} className="mt-2">
                <span className="text-xs text-slate-500 flex items-center gap-1 mb-1">
                  {Icon && <Icon size={12} />}
                  {config.label}
                </span>
                <div className="text-sm text-slate-700 bg-slate-50 p-2 rounded space-y-1">
                  {Object.entries(value).map(([subKey, subValue]) => (
                    subValue !== null && subValue !== undefined && (
                      <div key={subKey} className="flex justify-between">
                        <span className="text-slate-500 capitalize">{subKey.replace(/_/g, ' ')}:</span>
                        <span className="text-slate-800">{renderValue(subValue)}</span>
                      </div>
                    )
                  ))}
                </div>
              </div>
            );
          }

          // Handle strings/numbers
          return (
            <div key={key} className="flex justify-between items-start">
              <span className="text-sm text-slate-600 flex items-center gap-1">
                {Icon && <Icon size={12} />}
                {config.label}
              </span>
              <span className="text-sm text-slate-800 text-right max-w-[60%]">{renderValue(value)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// PDF Viewer Component - uses native browser PDF viewer
const PDFViewer = ({ url }) => {
  const [pdfBlobUrl, setPdfBlobUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch PDF as blob to create local URL (avoids CORS issues with iframe)
  useEffect(() => {
    const fetchPdf = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch(url);
        if (response.status === 404) {
          throw new Error('File no longer available on server');
        }
        if (!response.ok) throw new Error('Failed to fetch PDF');
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        setPdfBlobUrl(blobUrl);
        setLoading(false);
      } catch (err) {
        console.error('PDF fetch error:', err);
        setError(err.message || 'Failed to load PDF');
        setLoading(false);
      }
    };
    fetchPdf();
    
    return () => {
      if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
    };
  }, [url]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 w-full h-[70vh]">
        <RefreshCw size={32} className="animate-spin text-teal-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-slate-500">
        <FileText size={48} className="mx-auto mb-4 opacity-50" />
        <p className="text-red-500 mb-2">{error}</p>
        <p className="text-sm">File may have been deleted after server restart.</p>
        <p className="text-sm">Please re-upload the document.</p>
      </div>
    );
  }

  return (
    <iframe
      src={pdfBlobUrl}
      className="w-full h-[70vh] rounded-lg border-0"
      title="PDF Preview"
    />
  );
};

// Image Viewer Component with error handling - fetches as blob to avoid CORS
const ImageViewer = ({ url, alt }) => {
  const [imageBlobUrl, setImageBlobUrl] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchImage = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch(url);
        if (response.status === 404) {
          throw new Error('File no longer available on server');
        }
        if (!response.ok) throw new Error('Failed to fetch image');
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        setImageBlobUrl(blobUrl);
        setLoading(false);
      } catch (err) {
        console.error('Image fetch error:', err);
        setError(err.message || 'Failed to load image');
        setLoading(false);
      }
    };
    fetchImage();
    
    return () => {
      if (imageBlobUrl) URL.revokeObjectURL(imageBlobUrl);
    };
  }, [url]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw size={32} className="animate-spin text-teal-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-slate-500">
        <FileText size={48} className="mx-auto mb-4 opacity-50" />
        <p className="text-red-500 mb-2">{error}</p>
        <p className="text-sm">Please re-upload the document.</p>
      </div>
    );
  }

  return (
    <img 
      src={imageBlobUrl} 
      alt={alt}
      className="max-w-full max-h-[70vh] object-contain rounded-lg shadow-lg"
    />
  );
};

// Document Preview Modal
const DocumentPreview = ({ file, onClose }) => {
  if (!file) return null;

  const isImage = file.type?.startsWith('image/') || 
    ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'].some(ext => file.name?.toLowerCase().endsWith(ext));
  const isPDF = file.name?.toLowerCase().endsWith('.pdf');
  
  // Use API endpoint if taskId available, otherwise use local blob
  const previewUrl = file.taskId 
    ? `${API_URL}/file/${file.taskId}`
    : (file.previewUrl || (file.file ? URL.createObjectURL(file.file) : null));

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div 
        className="bg-white rounded-2xl max-w-5xl max-h-[90vh] w-full overflow-hidden shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <div className="flex items-center gap-3">
            {isImage ? <Image size={20} className="text-slate-500" /> : <FileText size={20} className="text-slate-500" />}
            <h3 className="font-bold text-slate-800 truncate max-w-md">{file.name}</h3>
          </div>
          <div className="flex items-center gap-2">
            {previewUrl && (
              <a
                href={previewUrl}
                download={file.name}
                className="p-2 rounded-lg text-slate-500 hover:text-teal-600 hover:bg-teal-50 transition-colors"
                title="Download"
                onClick={e => e.stopPropagation()}
              >
                <Download size={20} />
              </a>
            )}
            <button
              onClick={onClose}
              className="p-2 rounded-lg text-slate-500 hover:text-red-600 hover:bg-red-50 transition-colors"
            >
              <X size={20} />
            </button>
          </div>
        </div>
        
        {/* Content */}
        <div className="p-4 max-h-[calc(90vh-80px)] overflow-auto bg-slate-100 flex items-center justify-center min-h-[60vh]">
          {isImage && previewUrl ? (
            <ImageViewer url={previewUrl} alt={file.name} />
          ) : isPDF && previewUrl ? (
            <PDFViewer url={previewUrl} />
          ) : (
            <div className="text-center py-12 text-slate-500">
              <FileText size={48} className="mx-auto mb-4 opacity-50" />
              <p>Preview not available</p>
              {previewUrl && (
                <a 
                  href={previewUrl} 
                  download={file.name}
                  className="text-teal-600 hover:underline mt-2 inline-block"
                >
                  Download file
                </a>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// Validation section
const ValidationSection = ({ validation }) => {
  if (!validation) return null;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-4 flex items-center gap-2">
        <Shield size={14} className="text-teal-600" />
        Validation
      </h3>

      {/* Passed checks */}
      {validation.checks_passed?.length > 0 && (
        <div className="mb-4">
          <p className="text-xs font-bold text-emerald-600 mb-2">Passed</p>
          <div className="flex flex-wrap gap-2">
            {validation.checks_passed.map((check, i) => (
              <span key={i} className="inline-flex items-center gap-1 px-2 py-1 bg-emerald-50 text-emerald-700 text-xs rounded-full">
                <CheckCircle size={12} />
                {check}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Failed checks */}
      {validation.checks_failed?.length > 0 && (
        <div className="mb-4">
          <p className="text-xs font-bold text-red-600 mb-2">Failed</p>
          <div className="flex flex-wrap gap-2">
            {validation.checks_failed.map((check, i) => (
              <span key={i} className="inline-flex items-center gap-1 px-2 py-1 bg-red-50 text-red-700 text-xs rounded-full">
                <AlertCircle size={12} />
                {check}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Errors */}
      {validation.errors?.length > 0 && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-xs font-bold text-red-600 mb-1">Errors</p>
          {validation.errors.map((err, i) => (
            <p key={i} className="text-sm text-red-800">• {err}</p>
          ))}
        </div>
      )}

      {/* Warnings */}
      {validation.warnings?.length > 0 && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
          <p className="text-xs font-bold text-amber-600 mb-1">Warnings</p>
          {validation.warnings.map((warn, i) => (
            <p key={i} className="text-sm text-amber-800">• {warn}</p>
          ))}
        </div>
      )}

      {/* Extracted metadata */}
      {validation.extracted_data && Object.keys(validation.extracted_data).length > 0 && (
        <div className="mt-4 pt-4 border-t border-slate-100">
          <p className="text-xs font-bold text-slate-500 mb-2">Extracted Data</p>
          <div className="space-y-2 text-sm">
            {Object.entries(validation.extracted_data).map(([key, value]) => (
              <div key={key} className="flex justify-between">
                <span className="text-slate-600">{key.replace(/_/g, ' ')}</span>
                <span className="font-mono text-slate-800 truncate max-w-[200px]" title={String(value)}>
                  {String(value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// Main App
function App() {
  // Load initial state from localStorage
  const [files, setFiles] = useState(() => {
    try {
      const saved = localStorage.getItem('docVerification_files');
      if (saved) {
        const parsed = JSON.parse(saved);
        // Only restore completed/error files, not pending ones
        return parsed.filter(f => f.status === 'completed' || f.status === 'error');
      }
    } catch (e) {
      console.error('Failed to load saved files:', e);
    }
    return [];
  });
  
  const [selectedFileId, setSelectedFileId] = useState(() => {
    try {
      return localStorage.getItem('docVerification_selectedId') || null;
    } catch (e) {
      return null;
    }
  });
  
  const [isDragging, setIsDragging] = useState(false);
  const [previewFile, setPreviewFile] = useState(null);

  // Export single file report
  const exportFileReport = useCallback((file, format = 'json') => {
    if (!file?.result) return;
    
    const report = {
      file_name: file.name,
      processed_at: file.result.timestamp,
      decision: file.result.decision,
      decision_reason: file.result.decision_reason,
      confidence: file.result.confidence,
      document_type: file.result.analysis?.document_type,
      document_type_ua: file.result.analysis?.document_type_ua,
      red_flags: file.result.red_flags,
      warnings: file.result.warnings,
      analysis: file.result.analysis,
      validation: file.result.validation,
    };
    
    if (format === 'html') {
      const html = generateHTMLReport([report], false);
      const blob = new Blob([html], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${file.name.replace(/\.[^/.]+$/, '')}_${new Date().toISOString().slice(0,10)}.html`;
      a.click();
      URL.revokeObjectURL(url);
    } else {
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${file.name.replace(/\.[^/.]+$/, '')}_${new Date().toISOString().slice(0,10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
  }, []);

  // Generate HTML report
  const generateHTMLReport = (fileReports, isBatch = true) => {
    const decisionColors = {
      ACCEPT: { bg: '#d1fae5', text: '#065f46', border: '#6ee7b7' },
      REVIEW: { bg: '#fef3c7', text: '#92400e', border: '#fcd34d' },
      REJECT: { bg: '#fee2e2', text: '#991b1b', border: '#fca5a5' },
    };

    const summary = isBatch ? {
      total: fileReports.length,
      accepted: fileReports.filter(f => f.decision === 'ACCEPT').length,
      review: fileReports.filter(f => f.decision === 'REVIEW').length,
      rejected: fileReports.filter(f => f.decision === 'REJECT').length,
    } : null;

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Document Verification Report - ${new Date().toLocaleDateString()}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; color: #1e293b; line-height: 1.5; }
    .container { max-width: 1000px; margin: 0 auto; padding: 2rem; }
    .header { text-align: center; margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 2px solid #e2e8f0; }
    .header h1 { color: #0f766e; font-size: 1.75rem; margin-bottom: 0.5rem; }
    .header .date { color: #64748b; font-size: 0.875rem; }
    .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }
    .summary-card { background: white; border-radius: 0.75rem; padding: 1rem; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .summary-card .number { font-size: 2rem; font-weight: bold; }
    .summary-card .label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; }
    .summary-card.accept .number { color: #059669; }
    .summary-card.review .number { color: #d97706; }
    .summary-card.reject .number { color: #dc2626; }
    .file-card { background: white; border-radius: 0.75rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }
    .file-header { padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; }
    .file-name { font-weight: 600; font-size: 1rem; }
    .decision-badge { padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; border: 1px solid; }
    .file-body { padding: 1.5rem; }
    .section { margin-bottom: 1.5rem; }
    .section:last-child { margin-bottom: 0; }
    .section-title { font-size: 0.75rem; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 0.75rem; }
    .info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; }
    .info-item { display: flex; justify-content: space-between; padding: 0.5rem; background: #f8fafc; border-radius: 0.375rem; }
    .info-label { color: #64748b; font-size: 0.875rem; }
    .info-value { font-weight: 500; font-size: 0.875rem; }
    .flags-list { list-style: none; }
    .flags-list li { padding: 0.5rem 0.75rem; margin-bottom: 0.5rem; border-radius: 0.375rem; font-size: 0.875rem; }
    .flags-list li.red-flag { background: #fee2e2; color: #991b1b; border-left: 3px solid #dc2626; }
    .flags-list li.warning { background: #fef3c7; color: #92400e; border-left: 3px solid #f59e0b; }
    .no-issues { color: #059669; font-size: 0.875rem; }
    .extracted-data { background: #f8fafc; border-radius: 0.5rem; padding: 1rem; }
    .extracted-item { display: flex; justify-content: space-between; padding: 0.375rem 0; border-bottom: 1px solid #e2e8f0; font-size: 0.875rem; }
    .extracted-item:last-child { border-bottom: none; }
    .footer { text-align: center; margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 0.75rem; }
    @media print { body { background: white; } .container { max-width: none; } }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>📋 Document Verification Report</h1>
      <p class="date">Generated: ${new Date().toLocaleString()}</p>
    </div>
    
    ${summary ? `
    <div class="summary">
      <div class="summary-card">
        <div class="number">${summary.total}</div>
        <div class="label">Total Files</div>
      </div>
      <div class="summary-card accept">
        <div class="number">${summary.accepted}</div>
        <div class="label">Accepted</div>
      </div>
      <div class="summary-card review">
        <div class="number">${summary.review}</div>
        <div class="label">Review</div>
      </div>
      <div class="summary-card reject">
        <div class="number">${summary.rejected}</div>
        <div class="label">Rejected</div>
      </div>
    </div>
    ` : ''}
    
    ${fileReports.map(f => {
      const colors = decisionColors[f.decision] || decisionColors.REVIEW;
      const redFlags = f.red_flags || [];
      const warnings = f.warnings || [];
      const extractedData = f.analysis?.extracted_data || {};
      
      return `
    <div class="file-card">
      <div class="file-header">
        <span class="file-name">📄 ${f.file_name}</span>
        <span class="decision-badge" style="background:${colors.bg};color:${colors.text};border-color:${colors.border}">
          ${f.decision} (${Math.round((f.confidence || 0) * 100)}%)
        </span>
      </div>
      <div class="file-body">
        <div class="section">
          <div class="section-title">Document Information</div>
          <div class="info-grid">
            <div class="info-item">
              <span class="info-label">Type</span>
              <span class="info-value">${f.document_type || 'Unknown'}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Type (UA)</span>
              <span class="info-value">${f.document_type_ua || '—'}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Processed</span>
              <span class="info-value">${f.processed_at ? new Date(f.processed_at).toLocaleString() : '—'}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Reason</span>
              <span class="info-value">${f.decision_reason || '—'}</span>
            </div>
          </div>
        </div>
        
        <div class="section">
          <div class="section-title">Issues Found</div>
          ${redFlags.length === 0 && warnings.length === 0 ? '<p class="no-issues">✓ No issues found</p>' : `
          <ul class="flags-list">
            ${redFlags.map(flag => `<li class="red-flag">🚩 ${flag}</li>`).join('')}
            ${warnings.map(warn => `<li class="warning">⚠️ ${warn}</li>`).join('')}
          </ul>
          `}
        </div>
        
        ${Object.keys(extractedData).length > 0 ? `
        <div class="section">
          <div class="section-title">Extracted Data</div>
          <div class="extracted-data">
            ${Object.entries(extractedData).map(([key, value]) => {
              if (value === null || value === undefined) return '';
              const displayValue = typeof value === 'object' ? JSON.stringify(value) : String(value);
              return `<div class="extracted-item">
                <span class="info-label">${key.replace(/_/g, ' ')}</span>
                <span class="info-value">${displayValue}</span>
              </div>`;
            }).join('')}
          </div>
        </div>
        ` : ''}
      </div>
    </div>`;
    }).join('')}
    
    <div class="footer">
      Document Verification System • Report generated automatically
    </div>
  </div>
</body>
</html>`;
  };

  // Export all files report (JSON)
  const exportAllReportsJSON = useCallback(() => {
    const completedFiles = files.filter(f => f.status === 'completed' && f.result);
    if (completedFiles.length === 0) return;
    
    const report = {
      generated_at: new Date().toISOString(),
      total_files: completedFiles.length,
      summary: {
        accepted: completedFiles.filter(f => f.result.decision === 'ACCEPT').length,
        review: completedFiles.filter(f => f.result.decision === 'REVIEW').length,
        rejected: completedFiles.filter(f => f.result.decision === 'REJECT').length,
      },
      files: completedFiles.map(f => ({
        file_name: f.name,
        decision: f.result.decision,
        confidence: f.result.confidence,
        document_type: f.result.analysis?.document_type,
        document_type_ua: f.result.analysis?.document_type_ua,
        red_flags: f.result.red_flags,
        warnings: f.result.warnings,
        analysis: f.result.analysis,
        validation: f.result.validation,
      }))
    };
    
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `verification_report_${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [files]);

  // Export all files report (HTML)
  const exportAllReportsHTML = useCallback(() => {
    const completedFiles = files.filter(f => f.status === 'completed' && f.result);
    if (completedFiles.length === 0) return;
    
    const fileReports = completedFiles.map(f => ({
      file_name: f.name,
      processed_at: f.result.timestamp,
      decision: f.result.decision,
      decision_reason: f.result.decision_reason,
      confidence: f.result.confidence,
      document_type: f.result.analysis?.document_type,
      document_type_ua: f.result.analysis?.document_type_ua,
      red_flags: f.result.red_flags,
      warnings: f.result.warnings,
      analysis: f.result.analysis,
    }));
    
    const html = generateHTMLReport(fileReports, true);
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `verification_report_${new Date().toISOString().slice(0,10)}.html`;
    a.click();
    URL.revokeObjectURL(url);
  }, [files]);

  // Save to localStorage when files change
  useEffect(() => {
    try {
      // Only save completed files with results
      const toSave = files.filter(f => f.status === 'completed' || f.status === 'error');
      localStorage.setItem('docVerification_files', JSON.stringify(toSave));
    } catch (e) {
      console.error('Failed to save files:', e);
    }
  }, [files]);

  // Save selected file ID
  useEffect(() => {
    try {
      if (selectedFileId) {
        localStorage.setItem('docVerification_selectedId', selectedFileId);
      } else {
        localStorage.removeItem('docVerification_selectedId');
      }
    } catch (e) {
      console.error('Failed to save selection:', e);
    }
  }, [selectedFileId]);

  const selectedFile = files.find(f => f.id === selectedFileId);

  // Clear all files
  const clearAllFiles = useCallback(() => {
    setFiles([]);
    setSelectedFileId(null);
    localStorage.removeItem('docVerification_files');
    localStorage.removeItem('docVerification_selectedId');
  }, []);

  // Poll for task status
  const pollStatus = useCallback(async (taskId, fileId) => {
    const interval = setInterval(async () => {
      try {
        const statusRes = await axios.get(`${API_URL}/status/${taskId}`);
        const status = statusRes.data;

        if (status.status === 'completed') {
          clearInterval(interval);
          const resultRes = await axios.get(`${API_URL}/result/${taskId}`);
          setFiles(prev => prev.map(f => {
            if (f.id === fileId) {
              return { ...f, status: 'completed', result: resultRes.data };
            }
            return f;
          }));
        } else if (status.status === 'error') {
          clearInterval(interval);
          setFiles(prev => prev.map(f => {
            if (f.id === fileId) {
              return { ...f, status: 'error', error: status.error };
            }
            return f;
          }));
        } else {
          setFiles(prev => prev.map(f => {
            if (f.id === fileId) {
              return { ...f, status: status.status, stage: status.stage, progress: status.progress };
            }
            return f;
          }));
        }
      } catch (err) {
        clearInterval(interval);
        setFiles(prev => prev.map(f => {
          if (f.id === fileId) {
            return { ...f, status: 'error', error: err.message };
          }
          return f;
        }));
      }
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  // Upload file
  const uploadFile = useCallback(async (file) => {
    const fileId = Math.random().toString(36).substr(2, 9);
    
    setFiles(prev => [...prev, {
      id: fileId,
      name: file.name,
      type: file.type,
      status: 'pending',
      stage: 'Uploading...',
    }]);

    setSelectedFileId(fileId);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await axios.post(`${API_URL}/upload`, formData);
      const { task_id } = res.data;

      setFiles(prev => prev.map(f => {
        if (f.id === fileId) {
          return { ...f, taskId: task_id, status: 'processing', stage: 'Queued...' };
        }
        return f;
      }));

      pollStatus(task_id, fileId);

    } catch (err) {
      setFiles(prev => prev.map(f => {
        if (f.id === fileId) {
          return { ...f, status: 'error', error: err.message };
        }
        return f;
      }));
    }
  }, [pollStatus]);

  // Handle file drop/select
  const handleFiles = useCallback((fileList) => {
    Array.from(fileList).forEach(file => {
      uploadFile(file);
    });
  }, [uploadFile]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files?.length) {
      handleFiles(e.dataTransfer.files);
    }
  }, [handleFiles]);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleFileSelect = (e) => {
    if (e.target.files?.length) {
      handleFiles(e.target.files);
    }
    e.target.value = '';
  };

  const deleteFile = useCallback(async (fileId) => {
    const file = files.find(f => f.id === fileId);
    if (file?.taskId) {
      try {
        await axios.delete(`${API_URL}/task/${file.taskId}`);
      } catch (err) {
        console.error('Delete error:', err);
      }
    }
    setFiles(prev => prev.filter(f => f.id !== fileId));
    if (selectedFileId === fileId) {
      setSelectedFileId(null);
    }
  }, [files, selectedFileId]);

  const retryFile = useCallback(async (fileId) => {
    const file = files.find(f => f.id === fileId);
    if (!file?.taskId) return;

    try {
      // Call retry endpoint
      const res = await axios.post(`${API_URL}/retry/${file.taskId}`);
      
      // Update local state
      setFiles(prev => prev.map(f => {
        if (f.id === fileId) {
          return { 
            ...f, 
            status: 'processing', 
            stage: 'Retrying...', 
            result: null,
            error: null,
            retryCount: (f.retryCount || 0) + 1
          };
        }
        return f;
      }));

      // Start polling
      pollStatus(file.taskId, fileId);

    } catch (err) {
      console.error('Retry error:', err);
      setFiles(prev => prev.map(f => {
        if (f.id === fileId) {
          return { ...f, status: 'error', error: err.response?.data?.detail || err.message };
        }
        return f;
      }));
    }
  }, [files, pollStatus]);

  return (
    <div className="min-h-screen bg-slate-100">
      {/* Preview Modal */}
      {previewFile && (
        <DocumentPreview file={previewFile} onClose={() => setPreviewFile(null)} />
      )}

      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-teal-600 rounded-xl flex items-center justify-center">
              <CheckCircle size={24} className="text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-slate-800">Document Verification</h1>
              <p className="text-xs text-slate-500">Compensation Claims Processing v1.0</p>
            </div>
          </div>
          
          {/* Export dropdown */}
          {files.some(f => f.status === 'completed') && (
            <div className="relative group">
              <button
                className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-teal-600 hover:bg-teal-700 rounded-lg transition-colors"
              >
                <Download size={16} />
                Export All
              </button>
              <div className="absolute right-0 top-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10 min-w-[140px]">
                <button
                  onClick={exportAllReportsJSON}
                  className="block w-full px-4 py-2 text-sm text-left text-slate-700 hover:bg-teal-50 hover:text-teal-700 rounded-t-lg"
                >
                  📄 JSON
                </button>
                <button
                  onClick={exportAllReportsHTML}
                  className="block w-full px-4 py-2 text-sm text-left text-slate-700 hover:bg-teal-50 hover:text-teal-700 rounded-b-lg"
                >
                  🌐 HTML
                </button>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto p-6">
        <div className="grid grid-cols-12 gap-6">

          {/* Left column - Upload & File list */}
          <div className="col-span-4 space-y-4">
            {/* Upload zone */}
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => document.getElementById('fileInput').click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                isDragging 
                  ? 'border-teal-400 bg-teal-50' 
                  : 'border-slate-300 bg-white hover:border-teal-400 hover:bg-slate-50'
              }`}
            >
              <input
                id="fileInput"
                type="file"
                multiple
                accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff,.webp,.gif,.bmp"
                onChange={handleFileSelect}
                className="hidden"
              />
              <Upload size={40} className={`mx-auto mb-3 ${isDragging ? 'text-teal-500' : 'text-slate-400'}`} />
              <p className="text-sm font-medium text-slate-700">
                Drop files here or click to upload
              </p>
              <p className="text-xs text-slate-500 mt-1">
                PDF, JPG, PNG, TIFF
              </p>
            </div>

            {/* File list */}
            {files.length > 0 && (
              <div className="bg-white rounded-xl border border-slate-200 p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                    Files ({files.length})
                  </h3>
                  <button
                    onClick={clearAllFiles}
                    className="flex items-center gap-1 text-xs text-slate-400 hover:text-red-500 transition-colors"
                    title="Clear all files"
                  >
                    <XCircle size={14} />
                    Clear All
                  </button>
                </div>
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {files.map(file => (
                    <FileItem
                      key={file.id}
                      file={file}
                      isSelected={file.id === selectedFileId}
                      onClick={() => setSelectedFileId(file.id)}
                      onDelete={deleteFile}
                      onRetry={retryFile}
                      onView={(f) => setPreviewFile(f)}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right column - Results */}
          <div className="col-span-8">
            {selectedFile?.result ? (
              <div className="space-y-4">
                {/* Decision header */}
                <div className="bg-white rounded-xl border border-slate-200 p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-lg font-bold text-slate-800">{selectedFile.name}</h2>
                      <p className="text-sm text-slate-500 mt-1">
                        {selectedFile.result.decision_reason}
                        {selectedFile.retryCount > 0 && (
                          <span className="ml-2 text-xs text-slate-400">(attempt #{selectedFile.retryCount + 1})</span>
                        )}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* Preview button */}
                      <button
                        onClick={() => setPreviewFile(selectedFile)}
                        className="p-2 rounded-lg text-slate-500 hover:text-teal-600 hover:bg-teal-50 transition-colors"
                        title="Preview document"
                      >
                        <Eye size={18} />
                      </button>
                      {/* Export dropdown */}
                      <div className="relative group">
                        <button
                          className="p-2 rounded-lg text-slate-500 hover:text-teal-600 hover:bg-teal-50 transition-colors"
                          title="Export report"
                        >
                          <Download size={18} />
                        </button>
                        <div className="absolute right-0 top-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
                          <button
                            onClick={() => exportFileReport(selectedFile, 'json')}
                            className="block w-full px-4 py-2 text-sm text-left text-slate-700 hover:bg-teal-50 hover:text-teal-700 rounded-t-lg"
                          >
                            📄 Export JSON
                          </button>
                          <button
                            onClick={() => exportFileReport(selectedFile, 'html')}
                            className="block w-full px-4 py-2 text-sm text-left text-slate-700 hover:bg-teal-50 hover:text-teal-700 rounded-b-lg"
                          >
                            🌐 Export HTML
                          </button>
                        </div>
                      </div>
                      {/* Retry button */}
                      <button
                        onClick={() => retryFile(selectedFile.id)}
                        className="p-2 rounded-lg text-slate-500 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                        title="Retry processing"
                      >
                        <RotateCcw size={18} />
                      </button>
                      <DecisionBadge
                        decision={selectedFile.result.decision} 
                        confidence={selectedFile.result.confidence}
                      />
                    </div>
                  </div>
                  
                  {/* Red flags */}
                  {selectedFile.result.red_flags?.length > 0 && (
                    <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                      <p className="text-xs font-bold text-red-600 mb-2">🚩 Red Flags</p>
                      {selectedFile.result.red_flags.map((flag, i) => (
                        <p key={i} className="text-sm text-red-800">• {flag}</p>
                      ))}
                    </div>
                  )}

                  {/* Warnings */}
                  {selectedFile.result.warnings?.length > 0 && (
                    <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                      <p className="text-xs font-bold text-amber-600 mb-2">⚠️ Warnings</p>
                      {selectedFile.result.warnings.map((warn, i) => (
                        <p key={i} className="text-sm text-amber-800">• {warn}</p>
                      ))}
                    </div>
                  )}
                </div>

                {/* Details grid */}
                <div className="grid grid-cols-2 gap-4">
                  <AnalysisSection analysis={selectedFile.result.analysis} />
                  <ExtractedDataSection 
                    extractedData={selectedFile.result.analysis?.extracted_data}
                    documentType={selectedFile.result.analysis?.document_type}
                    warnings={[
                      ...(selectedFile.result.analysis?.warnings || []),
                      ...(selectedFile.result.validation?.warnings || []),
                      ...(selectedFile.result.warnings || [])
                    ]}
                  />
                </div>

                <ValidationSection validation={selectedFile.result.validation} />
              </div>
            ) : selectedFile?.status === 'processing' ? (
              <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
                <RefreshCw size={48} className="mx-auto text-teal-500 animate-spin mb-4" />
                <p className="text-lg font-medium text-slate-700">{selectedFile.stage || 'Processing...'}</p>
                <p className="text-sm text-slate-500 mt-2">This may take a few seconds</p>
              </div>
            ) : selectedFile?.status === 'error' ? (
              <div className="bg-white rounded-xl border border-red-200 p-12 text-center">
                <AlertCircle size={48} className="mx-auto text-red-500 mb-4" />
                <p className="text-lg font-medium text-red-700">Processing Error</p>
                <p className="text-sm text-red-500 mt-2">{selectedFile.error}</p>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
                <FileText size={48} className="mx-auto text-slate-300 mb-4" />
                <p className="text-lg font-medium text-slate-500">Select a file to view results</p>
                <p className="text-sm text-slate-400 mt-2">Upload documents to verify them</p>
              </div>
            )}
          </div>

        </div>
      </main>
    </div>
  );
}

export default App;