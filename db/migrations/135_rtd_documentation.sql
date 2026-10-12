-- ################################################################################################
-- # 135 - the paperwork behind a return to duty.
-- #
-- # The process was recorded as dates and a name: evaluated on, complied on, who the evaluator was.
-- # What an auditor asks for is the document behind them - the SAP's written determination, or the
-- # equivalent under whichever programme applies - and there was nowhere to put it.
-- #
-- # A date with no document behind it is somebody's word for it. That is fine while the process is
-- # running and not fine in the file afterwards.
-- ################################################################################################

ALTER TABLE driverprohibitions
    ADD COLUMN IF NOT EXISTS documentid VARCHAR(36) NULL AFTER rtdtestid;
