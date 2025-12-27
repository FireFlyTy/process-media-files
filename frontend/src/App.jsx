import React, { useState, useCallback, useEffect } from 'react';
import { Upload, FileText, Image, AlertCircle, CheckCircle, Clock, Trash2, RefreshCw, FileCheck, Shield, Camera, Building, User, Calendar, MapPin, Hash, RotateCcw, XCircle } from 'lucide-react';
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
const FileItem = ({ file, isSelected, onClick, onDelete, onRetry }) => {
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
  const progress = file.progress || 0;

  return (
    <div
      onClick={onClick}
      className={`relative overflow-hidden rounded-xl cursor-pointer transition-all border-2 ${
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

        <div className="flex items-center gap-1 flex-shrink-0">
          {statusIcons[file.status]}
          {canRetry && (
            <button
              onClick={(e) => { e.stopPropagation(); onRetry(file.id); }}
              className="p-1.5 rounded-lg text-slate-400 hover:text-blue-500 hover:bg-blue-50 transition-colors"
              title="Retry"
            >
              <RotateCcw size={14} />
            </button>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(file.id); }}
            className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
            title="Delete"
          >
            <Trash2 size={14} />
          </button>
        </div>
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
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-teal-600 rounded-xl flex items-center justify-center">
              <CheckCircle size={24} className="text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-slate-800">Document Verification</h1>
              <p className="text-xs text-slate-500">Compensation Claims Processing v2.0</p>
            </div>
          </div>
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