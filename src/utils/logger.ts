import winston from 'winston';
import DailyRotateFile from 'winston-daily-rotate-file';

const LOG_LEVEL = process.env.LOG_LEVEL || 'info';
const LOG_DIR = process.env.LOG_DIR || '/var/log/gpti';

// Format personnalisé avec timestamp et colorisation
const customFormat = winston.format.combine(
  winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
  winston.format.errors({ stack: true }),
  winston.format.splat(),
  winston.format.json()
);

// Format console avec couleurs
const consoleFormat = winston.format.combine(
  winston.format.colorize(),
  winston.format.timestamp({ format: 'HH:mm:ss' }),
  winston.format.printf(({ timestamp, level, message, ...meta }) => {
    let msg = `${timestamp} [${level}]: ${message}`;
    if (Object.keys(meta).length > 0) {
      msg += ` ${JSON.stringify(meta)}`;
    }
    return msg;
  })
);

// Transports
const transports: winston.transport[] = [
  // Console output
  new winston.transports.Console({
    format: consoleFormat,
    level: LOG_LEVEL,
  }),
];

// File transports (seulement en production)
if (process.env.NODE_ENV === 'production') {
  transports.push(
    // All logs
    new DailyRotateFile({
      filename: `${LOG_DIR}/gpti-%DATE%.log`,
      datePattern: 'YYYY-MM-DD',
      maxSize: '20m',
      maxFiles: '30d',
      format: customFormat,
    }),
    // Error logs
    new DailyRotateFile({
      filename: `${LOG_DIR}/gpti-error-%DATE%.log`,
      datePattern: 'YYYY-MM-DD',
      maxSize: '20m',
      maxFiles: '90d',
      level: 'error',
      format: customFormat,
    })
  );
}

// Créer le logger
export const logger = winston.createLogger({
  level: LOG_LEVEL,
  format: customFormat,
  transports,
  exitOnError: false,
});

// Créer des loggers contextuels
export const createContextLogger = (context: string) => {
  return logger.child({ context });
};

// Export pour compatibilité
export default logger;
